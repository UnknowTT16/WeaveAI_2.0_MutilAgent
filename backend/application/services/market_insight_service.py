"""市场洞察应用服务。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, cast
import asyncio
import json
import logging
import uuid

from core.config import settings
from core.exceptions import (
    ConflictError,
    GraphExecutionError,
    ResourceNotFoundError,
    ServiceUnavailableError,
)
from domain.agents.factory import agent_factory_for_graph
from domain.services import build_evidence_pack, build_memory_snapshot
from domain.workflows import create_market_insight_engine
from infrastructure.db import create_pg_client, create_session_event_sink, pg_is_configured
from infrastructure.exports import (
    append_rehearsal_metric,
    build_report_charts,
    write_roadshow_zip,
)
from repositories import (
    AgentResultRepository,
    DebateRepository,
    ReportRepository,
    SessionRepository,
    ToolInvocationRepository,
    WorkflowEventRepository,
)
from schemas.v2.requests import MarketInsightRequest
from schemas.v2.responses import MarketInsightResponse, WorkflowStatus

logger = logging.getLogger(__name__)


def _next_or_end(iterator: Any) -> Optional[dict[str, Any]]:
    """在线程中安全获取下一条事件，避免 StopIteration 进入 Future。"""
    try:
        return next(iterator)
    except StopIteration:
        return None


def _to_datetime(value: Any) -> Optional[datetime]:
    """将数据库或字符串时间统一转换为 datetime。"""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            return None
    else:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _build_demo_metrics(
    *,
    session_row: dict[str, Any],
    agent_results: list[dict[str, Any]],
    workflow_events: list[dict[str, Any]],
    tool_metrics: dict[str, Any],
) -> dict[str, Any]:
    """构建 Phase 5 评委看板核心指标。"""
    session_metrics = (
        tool_metrics.get("session") if isinstance(tool_metrics, dict) else {}
    )
    if not isinstance(session_metrics, dict):
        session_metrics = {}

    total_agents = len(agent_results)
    completed_agents = 0
    degraded_agents = 0
    failed_agents = 0

    for row in agent_results:
        status = str(row.get("status") or "").lower()
        if status == "completed":
            completed_agents += 1
        elif status in ("degraded", "skipped"):
            degraded_agents += 1
        elif status in ("failed", "error"):
            failed_agents += 1

    retry_count = 0
    guardrail_trigger_count = 0
    adaptive_degraded_count = 0
    for row in workflow_events:
        event_type = str(row.get("event_type") or "").lower()
        if event_type == "retry":
            retry_count += 1
        elif event_type == "guardrail_triggered":
            guardrail_trigger_count += 1
        elif event_type == "adaptive_concurrency":
            payload = row.get("payload")
            if isinstance(payload, dict):
                mode = str(payload.get("mode") or "").lower()
                if mode == "degraded":
                    adaptive_degraded_count += 1

    evidence_pack = session_row.get("evidence_pack")
    claims: list[dict[str, Any]] = []
    if isinstance(evidence_pack, dict):
        raw_claims = evidence_pack.get("claims")
        if isinstance(raw_claims, list):
            claims = [c for c in raw_claims if isinstance(c, dict)]

    evidence_claims_total = len(claims)
    evidence_claims_with_sources = 0
    for claim in claims:
        source_refs = claim.get("source_refs")
        if isinstance(source_refs, list) and len(source_refs) > 0:
            evidence_claims_with_sources += 1

    evidence_coverage_rate = (
        (evidence_claims_with_sources / evidence_claims_total)
        if evidence_claims_total > 0
        else 0.0
    )

    started_at = _to_datetime(session_row.get("started_at")) or _to_datetime(
        session_row.get("created_at")
    )
    completed_at = _to_datetime(session_row.get("completed_at"))
    session_status = str(session_row.get("status") or "").lower()
    duration_ms: Optional[int] = None
    if started_at is not None:
        end_dt = completed_at
        if end_dt is None and session_status == "running":
            end_dt = datetime.now(timezone.utc)
        if end_dt is not None:
            duration_ms = max(0, int((end_dt - started_at).total_seconds() * 1000))

    tool_error_rate = float(session_metrics.get("error_rate") or 0.0)

    penalty = 0.0
    penalty += failed_agents * 30
    penalty += degraded_agents * 12
    penalty += guardrail_trigger_count * 15
    penalty += adaptive_degraded_count * 6
    penalty += min(20, retry_count * 2)
    penalty += min(25, tool_error_rate * 25)
    stability_score = max(0.0, min(100.0, 100.0 - penalty))

    if stability_score >= 85:
        stability_level = "high"
    elif stability_score >= 65:
        stability_level = "medium"
    else:
        stability_level = "low"

    degrade_count = degraded_agents + guardrail_trigger_count + adaptive_degraded_count

    return {
        "total_duration_ms": duration_ms,
        "stability_score": round(stability_score, 2),
        "stability_level": stability_level,
        "evidence_coverage_rate": round(evidence_coverage_rate, 4),
        "evidence_claims_total": evidence_claims_total,
        "evidence_claims_with_sources": evidence_claims_with_sources,
        "degrade_count": degrade_count,
        "degrade_breakdown": {
            "agent_degraded_or_skipped": degraded_agents,
            "guardrail_triggered": guardrail_trigger_count,
            "adaptive_concurrency_degraded": adaptive_degraded_count,
        },
        "retry_count": retry_count,
        "failed_agents": failed_agents,
        "completed_agents": completed_agents,
        "total_agents": total_agents,
        "tool_total_calls": int(session_metrics.get("total_calls") or 0),
        "tool_error_rate": round(tool_error_rate, 4),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_initial_state(
    *,
    session_id: str,
    profile: dict[str, Any],
    request: MarketInsightRequest,
    debate_rounds: int,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "user_profile": profile,
        "debate_rounds": debate_rounds,
        "enable_followup": request.enable_followup,
        "enable_websearch": request.enable_websearch,
        "retry_max_attempts": request.retry_max_attempts,
        "retry_backoff_ms": request.retry_backoff_ms,
        "degrade_mode": request.degrade_mode,
    }


def _seed_session_row_if_needed(
    *,
    session_id: str,
    profile: dict[str, Any],
    config: dict[str, Any],
) -> None:
    """在流式/同步执行前同步写入 sessions，避免状态查询读到 not_found。"""
    if not pg_is_configured():
        return

    pg = None
    try:
        pg = create_pg_client()
        SessionRepository(pg).create_session(session_id, profile, config)
    except Exception as exc:
        logger.warning(f"会话预创建失败（可继续执行）session={session_id}: {exc}")
    finally:
        if pg is not None:
            try:
                pg.close()
            except Exception:
                pass


async def stream_market_insight_events(
    request: MarketInsightRequest,
    *,
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[dict[str, str]]:
    """生成 SSE 事件流。"""
    session_id = request.session_id or str(uuid.uuid4())
    profile_dict = request.profile.model_dump() if request.profile else {}
    debate_rounds = (
        request.debate_rounds
        if request.debate_rounds is not None
        else settings.default_debate_rounds
    )
    config_dict = {
        "debate_rounds": debate_rounds,
        "enable_followup": request.enable_followup,
        "enable_websearch": request.enable_websearch,
        "retry_max_attempts": request.retry_max_attempts,
        "retry_backoff_ms": request.retry_backoff_ms,
        "degrade_mode": request.degrade_mode,
    }

    _seed_session_row_if_needed(
        session_id=session_id,
        profile=profile_dict,
        config=config_dict,
    )

    sink = create_session_event_sink(
        session_id=session_id,
        profile=profile_dict,
        config=config_dict,
    )

    try:
        factory = agent_factory_for_graph()
        engine = create_market_insight_engine(
            agent_factory=factory,
            debate_rounds=debate_rounds,
            enable_followup=request.enable_followup,
            retry_max_attempts=request.retry_max_attempts,
            retry_backoff_ms=request.retry_backoff_ms,
            degrade_mode=request.degrade_mode,
            use_checkpointer=True,
        )
        initial_state = _build_initial_state(
            session_id=session_id,
            profile=profile_dict,
            request=request,
            debate_rounds=debate_rounds,
        )

        stream_iter = iter(engine.stream(initial_state))
        while True:
            if await is_disconnected():
                logger.info(f"客户端断开连接，session={session_id}")
                try:
                    stream_iter.close()
                except Exception:
                    pass
                break

            event = await asyncio.to_thread(_next_or_end, stream_iter)
            if event is None:
                break

            try:
                sink.on_event(event)
            except Exception:
                pass

            yield {
                "event": str(event.get("event", "message")),
                "data": json.dumps(event, ensure_ascii=False, default=str),
            }
            await asyncio.sleep(0)

    except GraphExecutionError as exc:
        logger.error(f"工作流执行失败: {exc}")
        payload = {
            "event": "error",
            "error": str(exc),
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
        }
        try:
            sink.on_event(payload)
        except Exception:
            pass
        yield {"event": "error", "data": json.dumps(payload, ensure_ascii=False)}
    except Exception as exc:
        logger.error(f"未知错误: {exc}")
        payload = {
            "event": "error",
            "error": f"系统错误: {str(exc)}",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
        }
        try:
            sink.on_event(payload)
        except Exception:
            pass
        yield {"event": "error", "data": json.dumps(payload, ensure_ascii=False)}
    finally:
        try:
            sink.close()
        except Exception:
            pass


async def generate_market_insight_payload(
    request: MarketInsightRequest,
) -> MarketInsightResponse:
    """同步生成完整市场洞察报告。"""
    session_id = request.session_id or str(uuid.uuid4())
    profile_dict = request.profile.model_dump() if request.profile else {}
    debate_rounds = (
        request.debate_rounds
        if request.debate_rounds is not None
        else settings.default_debate_rounds
    )
    config_dict = {
        "debate_rounds": debate_rounds,
        "enable_followup": request.enable_followup,
        "enable_websearch": request.enable_websearch,
        "retry_max_attempts": request.retry_max_attempts,
        "retry_backoff_ms": request.retry_backoff_ms,
        "degrade_mode": request.degrade_mode,
    }

    _seed_session_row_if_needed(
        session_id=session_id,
        profile=profile_dict,
        config=config_dict,
    )

    factory = agent_factory_for_graph()
    engine = create_market_insight_engine(
        agent_factory=factory,
        debate_rounds=debate_rounds,
        enable_followup=request.enable_followup,
        retry_max_attempts=request.retry_max_attempts,
        retry_backoff_ms=request.retry_backoff_ms,
        degrade_mode=request.degrade_mode,
        use_checkpointer=False,
    )
    initial_state = _build_initial_state(
        session_id=session_id,
        profile=profile_dict,
        request=request,
        debate_rounds=debate_rounds,
    )
    result = await asyncio.to_thread(engine.invoke, initial_state)
    report_html_url = result.get("report_html_url")

    if pg_is_configured():
        pg = None
        try:
            pg = create_pg_client()
            session_repo = SessionRepository(pg)
            agent_result_repo = AgentResultRepository(pg)

            update_fields: dict[str, Any] = {
                "status": "completed",
                "phase": "complete",
                "current_debate_round": int(result.get("current_debate_round") or 0),
                "synthesized_report": result.get("synthesized_report") or "",
                "completed_at": datetime.now(),
            }

            if isinstance(result.get("evidence_pack"), dict):
                update_fields["evidence_pack"] = result.get("evidence_pack")
                update_fields["evidence_generated_at"] = datetime.now()
            if isinstance(result.get("memory_snapshot"), dict):
                update_fields["memory_snapshot"] = result.get("memory_snapshot")
                update_fields["memory_snapshot_generated_at"] = datetime.now()

            session_repo.update_session_fields(session_id, update_fields)

            for row in result.get("agent_results", []):
                agent_name = getattr(row, "agent_name", None)
                if not agent_name:
                    continue
                agent_result_repo.upsert_agent_result(
                    session_id,
                    str(agent_name),
                    {
                        "status": "completed"
                        if not getattr(row, "error", None)
                        else "failed",
                        "content": getattr(row, "content", "") or "",
                        "thinking": getattr(row, "thinking", None),
                        "sources": getattr(row, "sources", []) or [],
                        "confidence": getattr(row, "confidence", 1.0),
                        "duration_ms": int(getattr(row, "duration_ms", 0) or 0),
                        "error_message": getattr(row, "error", None),
                        "completed_at": datetime.now(),
                    },
                )
        except Exception as exc:
            logger.warning(f"同步模式回写会话状态失败: {exc}")
        finally:
            if pg is not None:
                try:
                    pg.close()
                except Exception:
                    pass

    return MarketInsightResponse(
        session_id=session_id,
        status=WorkflowStatus.COMPLETED,
        report=result.get("synthesized_report", ""),
        report_html_url=report_html_url,
        evidence_pack=result.get("evidence_pack"),
        memory_snapshot=result.get("memory_snapshot"),
        agent_results=[
            {
                "agent_name": row.agent_name,
                "content": row.content,
                "sources": row.sources,
                "duration_ms": row.duration_ms,
            }
            for row in result.get("agent_results", [])
        ],
        debate_summary={
            "total_exchanges": len(result.get("debate_exchanges", [])),
            "rounds": result.get("current_debate_round", 0),
        },
        created_at=datetime.now(),
    )


async def get_workflow_status_payload(session_id: str) -> dict[str, Any]:
    """查询工作流状态。"""
    if not pg_is_configured():
        return {
            "session_id": session_id,
            "status": "unknown",
            "message": "数据库未配置，状态查询不可用",
        }

    pg = create_pg_client()
    try:
        session_repo = SessionRepository(pg)
        agent_result_repo = AgentResultRepository(pg)
        debate_repo = DebateRepository(pg)
        workflow_event_repo = WorkflowEventRepository(pg)
        tool_invocation_repo = ToolInvocationRepository(pg)
        report_repo = ReportRepository()

        try:
            session_row = session_repo.get_session_row(session_id)
        except Exception as exc:
            logger.error(f"状态查询失败 session={session_id}: {exc}")
            return {
                "session_id": session_id,
                "status": "error",
                "message": "状态查询失败，请稍后重试",
            }

        if not session_row:
            return {
                "session_id": session_id,
                "status": "not_found",
                "message": "会话不存在",
            }

        report_path = report_repo.get_report_file_path(session_id)
        if not report_path.exists() and session_row.get("synthesized_report"):
            try:
                report_repo.write_html_report(
                    session_id=session_id,
                    report_markdown=session_row.get("synthesized_report") or "",
                    profile=session_row.get("profile") or {},
                )
            except Exception as exc:
                logger.warning(f"按需生成 HTML 报告失败: {exc}")

        if report_path.exists():
            session_row["report_html_url"] = (
                f"/api/v2/market-insight/report/{session_id}.html"
            )

        agent_results = agent_result_repo.list_agent_results(session_id)
        debate_exchanges = debate_repo.list_debate_exchanges(session_id)
        workflow_events = workflow_event_repo.list_workflow_events(
            session_id,
            limit=200,
        )
        tool_invocations = tool_invocation_repo.list_tool_invocations(session_id)
        tool_metrics = tool_invocation_repo.aggregate_tool_metrics(session_id)

        update_fields: dict[str, Any] = {}
        profile = (
            session_row.get("profile")
            if isinstance(session_row.get("profile"), dict)
            else {}
        )
        synthesized_report = str(session_row.get("synthesized_report") or "")
        if synthesized_report:
            if not isinstance(session_row.get("evidence_pack"), dict):
                try:
                    evidence_pack = build_evidence_pack(
                        session_id=session_id,
                        profile=profile,
                        agent_results=agent_results,
                        debate_exchanges=debate_exchanges,
                        final_report=synthesized_report,
                    )
                    session_row["evidence_pack"] = evidence_pack
                    update_fields["evidence_pack"] = evidence_pack
                    update_fields["evidence_generated_at"] = datetime.now()
                except Exception as exc:
                    logger.warning(f"按需回补 Evidence Pack 失败: {exc}")

            if not isinstance(session_row.get("memory_snapshot"), dict):
                try:
                    memory_snapshot = build_memory_snapshot(
                        session_id=session_id,
                        profile=profile,
                        agent_results=agent_results,
                        debate_exchanges=debate_exchanges,
                        final_report=synthesized_report,
                    )
                    session_row["memory_snapshot"] = memory_snapshot
                    update_fields["memory_snapshot"] = memory_snapshot
                    update_fields["memory_snapshot_generated_at"] = datetime.now()
                except Exception as exc:
                    logger.warning(f"按需回补记忆快照失败: {exc}")

        if update_fields:
            try:
                session_repo.update_session_fields(session_id, update_fields)
            except Exception as exc:
                logger.warning(f"回写 Phase 3 结构化结果失败: {exc}")

        demo_metrics = _build_demo_metrics(
            session_row=session_row,
            agent_results=agent_results,
            workflow_events=workflow_events,
            tool_metrics=tool_metrics,
        )
        report_charts = build_report_charts(
            session_id=session_id,
            profile=profile,
            demo_metrics=demo_metrics,
            tool_metrics=tool_metrics,
        )

        session_status = str(session_row.get("status") or "").lower()
        if synthesized_report and session_status in ("completed", "failed", "cancelled"):
            try:
                report_repo.write_html_report(
                    session_id=session_id,
                    report_markdown=synthesized_report,
                    profile=profile,
                    chart_bundle=report_charts,
                )
                session_row["report_html_url"] = (
                    f"/api/v2/market-insight/report/{session_id}.html"
                )
            except Exception as exc:
                logger.warning(f"写入图表增强 HTML 报告失败: {exc}")

        if session_status in ("completed", "failed", "cancelled"):
            try:
                append_rehearsal_metric(
                    {
                        "session_id": session_id,
                        "status": session_status,
                        "phase": session_row.get("phase"),
                        "profile": profile,
                        "demo_metrics": demo_metrics,
                    }
                )
            except Exception as exc:
                logger.warning(f"写入 Phase 5 彩排日志失败: {exc}")

        return {
            "session": session_row,
            "agent_results": agent_results,
            "debate_exchanges": debate_exchanges,
            "workflow_events": workflow_events,
            "tool_invocations": tool_invocations,
            "tool_metrics": tool_metrics,
            "demo_metrics": demo_metrics,
            "report_charts": report_charts,
        }
    finally:
        try:
            pg.close()
        except Exception:
            pass


async def list_history_sessions_payload(
    *,
    limit: int,
    offset: int,
    status: Optional[str],
) -> dict[str, Any]:
    """读取历史会话摘要。"""
    if not pg_is_configured():
        return {
            "sessions": [],
            "limit": limit,
            "offset": offset,
            "next_offset": offset,
            "has_more": False,
            "message": "数据库未配置，历史会话不可用",
        }

    safe_limit = max(1, min(int(limit), 100))
    safe_offset = max(0, int(offset))
    normalized_status = str(status).strip().lower() if status else None

    pg = create_pg_client()
    try:
        raw_rows = SessionRepository(pg).list_sessions_summary(
            limit=safe_limit + 1,
            offset=safe_offset,
            status=normalized_status,
        )
    finally:
        try:
            pg.close()
        except Exception:
            pass

    has_more = len(raw_rows) > safe_limit
    rows = raw_rows[:safe_limit]
    sessions: list[dict[str, Any]] = []
    for row in rows:
        session_id = str(row.get("id") or "")
        profile = row.get("profile") if isinstance(row.get("profile"), dict) else {}
        if not profile:
            profile = {
                "target_market": row.get("target_market"),
                "supply_chain": row.get("supply_chain"),
                "seller_type": row.get("seller_type"),
                "min_price": row.get("min_price"),
                "max_price": row.get("max_price"),
            }

        item = {
            "id": session_id,
            "status": row.get("status"),
            "phase": row.get("phase"),
            "current_debate_round": row.get("current_debate_round") or 0,
            "created_at": row.get("created_at"),
            "started_at": row.get("started_at"),
            "completed_at": row.get("completed_at"),
            "profile": profile,
            "debate_rounds": row.get("debate_rounds"),
            "enable_followup": row.get("enable_followup"),
            "enable_websearch": row.get("enable_websearch"),
            "error_message": row.get("error_message"),
            "report_preview": row.get("report_preview") or "",
            "has_report": bool(row.get("has_report")),
        }

        if item["has_report"] and session_id:
            item["report_html_url"] = f"/api/v2/market-insight/report/{session_id}.html"

        sessions.append(item)

    return {
        "sessions": sessions,
        "limit": safe_limit,
        "offset": safe_offset,
        "next_offset": safe_offset + len(sessions),
        "has_more": has_more,
        "status_filter": normalized_status,
    }


async def ensure_html_report_path(session_id: str) -> Path:
    """按需刷新并返回 HTML 报告路径。"""
    report_repo = ReportRepository()
    report_path = report_repo.get_report_file_path(session_id)

    if pg_is_configured():
        try:
            status_payload = await get_workflow_status_payload(session_id)
            raw_session = status_payload.get("session")
            session_row = (
                cast(dict[str, Any], raw_session)
                if isinstance(raw_session, dict)
                else None
            )
            if session_row and session_row.get("synthesized_report"):
                raw_chart_bundle = status_payload.get("report_charts")
                chart_bundle = (
                    cast(dict[str, Any], raw_chart_bundle)
                    if isinstance(raw_chart_bundle, dict)
                    else None
                )
                report_repo.write_html_report(
                    session_id=session_id,
                    report_markdown=session_row.get("synthesized_report") or "",
                    profile=session_row.get("profile")
                    if isinstance(session_row.get("profile"), dict)
                    else {},
                    chart_bundle=chart_bundle,
                )
        except Exception as exc:
            logger.warning(f"按需刷新 HTML 报告失败: {exc}")

    if not report_path.exists():
        raise ResourceNotFoundError("HTML 报告不存在", {"session_id": session_id})

    return report_path


async def build_roadshow_package(session_id: str) -> Path:
    """导出路演 ZIP 包。"""
    status_payload = await get_workflow_status_payload(session_id)

    if status_payload.get("status") == "unknown":
        raise ServiceUnavailableError(
            "数据库未配置，无法导出路演包",
            {"session_id": session_id},
        )

    if status_payload.get("status") == "not_found":
        raise ResourceNotFoundError("会话不存在", {"session_id": session_id})

    session_row = status_payload.get("session")
    if not isinstance(session_row, dict):
        raise ResourceNotFoundError("会话不存在", {"session_id": session_id})

    report_markdown = str(session_row.get("synthesized_report") or "").strip()
    if not report_markdown:
        raise ConflictError("会话尚未生成可导出报告", {"session_id": session_id})

    report_repo = ReportRepository()
    report_path = report_repo.get_report_file_path(session_id)
    if not report_path.exists():
        try:
            report_repo.write_html_report(
                session_id=session_id,
                report_markdown=report_markdown,
                profile=session_row.get("profile")
                if isinstance(session_row.get("profile"), dict)
                else {},
            )
        except Exception as exc:
            logger.error(f"导出路演包时生成 HTML 报告失败: {exc}")
            raise RuntimeError("生成 HTML 报告失败") from exc

    if not report_path.exists():
        raise RuntimeError("HTML 报告不存在，无法导出路演包")

    evidence_pack = (
        session_row.get("evidence_pack")
        if isinstance(session_row.get("evidence_pack"), dict)
        else {}
    )
    memory_snapshot = (
        session_row.get("memory_snapshot")
        if isinstance(session_row.get("memory_snapshot"), dict)
        else {}
    )
    demo_metrics = (
        cast(dict[str, Any], status_payload.get("demo_metrics"))
        if isinstance(status_payload.get("demo_metrics"), dict)
        else {}
    )
    tool_metrics = (
        cast(dict[str, Any], status_payload.get("tool_metrics"))
        if isinstance(status_payload.get("tool_metrics"), dict)
        else {}
    )
    workflow_events = (
        [
            cast(dict[str, Any], row)
            for row in status_payload.get("workflow_events", [])
            if isinstance(row, dict)
        ]
        if isinstance(status_payload.get("workflow_events"), list)
        else []
    )
    report_charts = (
        cast(dict[str, Any], status_payload.get("report_charts"))
        if isinstance(status_payload.get("report_charts"), dict)
        else {}
    )

    try:
        report_repo.write_html_report(
            session_id=session_id,
            report_markdown=report_markdown,
            profile=session_row.get("profile")
            if isinstance(session_row.get("profile"), dict)
            else {},
            chart_bundle=report_charts,
        )
    except Exception as exc:
        logger.warning(f"导出路演包时写入图表增强 HTML 失败: {exc}")
        report_path = report_repo.get_report_file_path(session_id)

    return write_roadshow_zip(
        session_id=session_id,
        session_row=session_row,
        report_markdown=report_markdown,
        report_html_path=report_path,
        evidence_pack=evidence_pack,
        memory_snapshot=memory_snapshot,
        demo_metrics=demo_metrics,
        tool_metrics=tool_metrics,
        workflow_events=workflow_events,
        report_charts=report_charts,
    )


def get_health_payload() -> dict[str, Any]:
    """v2 API 健康检查。"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "features": {
            "multi_agent": True,
            "debate": True,
            "streaming": True,
        },
    }
