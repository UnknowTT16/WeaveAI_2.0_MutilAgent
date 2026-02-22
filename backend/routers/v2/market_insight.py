# backend/routers/v2/market_insight.py
"""
v2 市场洞察 API 端点

提供 SSE 流式接口，支持 Supervisor-Worker + 多轮辩论 架构
"""

from typing import Optional, Any, cast
from datetime import datetime, timezone
import json
import logging
import asyncio
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, FileResponse
from sse_starlette.sse import EventSourceResponse

from core.config import settings
from core.evidence_pack import build_evidence_pack
from core.graph_engine import create_market_insight_engine
from core.exceptions import GraphExecutionError
from schemas.v2.requests import MarketInsightRequest
from schemas.v2.responses import MarketInsightResponse, WorkflowStatus
from agents.factory import agent_factory_for_graph
from database.event_sink import create_session_event_sink
from database.pg_client import pg_is_configured, create_pg_client
from memory import build_memory_snapshot
from utils.report_export import get_report_file_path, write_html_report
from utils.rehearsal_log import append_rehearsal_metric
from utils.roadshow_export import write_roadshow_zip
from utils.report_charts import build_report_charts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market-insight", tags=["Market Insight v2"])


def _next_or_end(iterator) -> Optional[dict[str, Any]]:
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


def _seed_session_row_if_needed(
    *, session_id: str, profile: dict[str, Any], config: dict[str, Any]
) -> None:
    """在流式/同步执行前同步写入 sessions，避免状态查询读到 not_found。"""
    if not pg_is_configured():
        return

    pg = None
    try:
        pg = create_pg_client()
        pg.create_session(session_id, profile, config)
    except Exception as e:
        logger.warning(f"会话预创建失败（可继续执行）session={session_id}: {e}")
    finally:
        if pg is not None:
            try:
                pg.close()
            except Exception:
                pass


# ============================================
# SSE 流式端点
# ============================================


@router.post("/stream")
async def stream_market_insight(http_request: Request, request: MarketInsightRequest):
    """
    流式生成市场洞察报告

    使用 Server-Sent Events (SSE) 推送实时进度：
    - orchestrator_start: 工作流开始
    - agent_start: Agent 开始执行
    - agent_chunk: Agent 输出增量
    - agent_thinking: Agent 思考过程
    - tool_start/tool_end: 工具调用生命周期
    - retry: 节点重试
    - agent_end: Agent 执行完成
    - agent_error: Agent 执行失败
    - debate_round_start: 辩论轮次开始
    - debate_round_end: 辩论轮次结束
    - agent_challenge: 发起质疑
    - agent_challenge_end: 质疑完成（含完整内容）
    - agent_respond: 回应质疑
    - agent_respond_end: 回应完成（含完整内容）
    - agent_followup: 二次追问
    - agent_followup_end: 二次追问完成
    - orchestrator_end: 工作流完成（含 final_report / report_html_url）
    - error: 系统错误
    """

    async def event_generator():
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

        # 同步预创建会话，保证中断后 status 仍能查到基础状态。
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
            # 创建 Agent 工厂
            factory = agent_factory_for_graph()

            # 创建图引擎
            engine = create_market_insight_engine(
                agent_factory=factory,
                debate_rounds=debate_rounds,
                enable_followup=request.enable_followup,
                retry_max_attempts=request.retry_max_attempts,
                retry_backoff_ms=request.retry_backoff_ms,
                degrade_mode=request.degrade_mode,
                use_checkpointer=True,
            )

            # 准备初始状态
            initial_state = {
                "session_id": session_id,
                "user_profile": profile_dict,
                "debate_rounds": debate_rounds,
                "enable_followup": request.enable_followup,
                "enable_websearch": request.enable_websearch,
                "retry_max_attempts": request.retry_max_attempts,
                "retry_backoff_ms": request.retry_backoff_ms,
                "degrade_mode": request.degrade_mode,
            }

            # 流式执行（将同步迭代放在线程中，避免阻塞事件循环）
            stream_iter = iter(engine.stream(initial_state))
            while True:
                if await http_request.is_disconnected():
                    logger.info(f"客户端断开连接，session={session_id}")
                    try:
                        stream_iter.close()
                    except Exception:
                        pass
                    break

                event = await asyncio.to_thread(_next_or_end, stream_iter)
                if event is None:
                    break

                # 落库（不阻塞 SSE）
                try:
                    sink.on_event(event)
                except Exception:
                    pass

                # 转换为 SSE 格式
                sse_data = json.dumps(event, ensure_ascii=False, default=str)
                yield {
                    "event": event.get("event", "message"),
                    "data": sse_data,
                }

                # 让出控制权，避免阻塞
                await asyncio.sleep(0)

        except GraphExecutionError as e:
            logger.error(f"工作流执行失败: {e}")
            try:
                sink.on_event(
                    {
                        "event": "error",
                        "error": str(e),
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            except Exception:
                pass
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "event": "error",
                        "error": str(e),
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                    },
                    ensure_ascii=False,
                ),
            }
        except Exception as e:
            logger.error(f"未知错误: {e}")
            try:
                sink.on_event(
                    {
                        "event": "error",
                        "error": f"系统错误: {str(e)}",
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            except Exception:
                pass
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "event": "error",
                        "error": f"系统错误: {str(e)}",
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                    },
                    ensure_ascii=False,
                ),
            }

        finally:
            try:
                sink.close()
            except Exception:
                pass

    return EventSourceResponse(
        event_generator(),
        ping=15,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================
# 同步端点 (非流式)
# ============================================


@router.post("/generate", response_model=MarketInsightResponse)
async def generate_market_insight(request: MarketInsightRequest):
    """
    同步生成市场洞察报告 (非流式)

    适用于不需要实时进度的场景，返回完整报告
    """
    session_id = request.session_id or str(uuid.uuid4())
    profile_dict = request.profile.model_dump() if request.profile else {}
    gen_debate_rounds = (
        request.debate_rounds
        if request.debate_rounds is not None
        else settings.default_debate_rounds
    )
    config_dict = {
        "debate_rounds": gen_debate_rounds,
        "enable_followup": request.enable_followup,
        "enable_websearch": request.enable_websearch,
        "retry_max_attempts": request.retry_max_attempts,
        "retry_backoff_ms": request.retry_backoff_ms,
        "degrade_mode": request.degrade_mode,
    }

    # 同步模式也预创建会话，确保 /status/{session_id} 可查询。
    _seed_session_row_if_needed(
        session_id=session_id,
        profile=profile_dict,
        config=config_dict,
    )

    try:
        # 创建 Agent 工厂
        factory = agent_factory_for_graph()

        # 创建图引擎
        engine = create_market_insight_engine(
            agent_factory=factory,
            debate_rounds=gen_debate_rounds,
            enable_followup=request.enable_followup,
            retry_max_attempts=request.retry_max_attempts,
            retry_backoff_ms=request.retry_backoff_ms,
            degrade_mode=request.degrade_mode,
            use_checkpointer=False,  # 同步模式不需要 checkpointer
        )

        # 准备初始状态
        initial_state = {
            "session_id": session_id,
            "user_profile": profile_dict,
            "debate_rounds": gen_debate_rounds,
            "enable_followup": request.enable_followup,
            "enable_websearch": request.enable_websearch,
            "retry_max_attempts": request.retry_max_attempts,
            "retry_backoff_ms": request.retry_backoff_ms,
            "degrade_mode": request.degrade_mode,
        }

        # 执行工作流（放在线程中，避免阻塞事件循环）
        result = await asyncio.to_thread(engine.invoke, initial_state)
        report_html_url = result.get("report_html_url")

        # 同步模式回写关键字段，保证 status 接口可观测。
        if pg_is_configured():
            pg = None
            try:
                pg = create_pg_client()
                update_fields: dict[str, Any] = {
                    "status": "completed",
                    "phase": "complete",
                    "current_debate_round": int(
                        result.get("current_debate_round") or 0
                    ),
                    "synthesized_report": result.get("synthesized_report") or "",
                    "completed_at": datetime.now(),
                }

                if isinstance(result.get("evidence_pack"), dict):
                    update_fields["evidence_pack"] = result.get("evidence_pack")
                    update_fields["evidence_generated_at"] = datetime.now()
                if isinstance(result.get("memory_snapshot"), dict):
                    update_fields["memory_snapshot"] = result.get("memory_snapshot")
                    update_fields["memory_snapshot_generated_at"] = datetime.now()

                pg.update_session_fields(session_id, update_fields)

                for row in result.get("agent_results", []):
                    agent_name = getattr(row, "agent_name", None)
                    if not agent_name:
                        continue
                    pg.upsert_agent_result(
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
            except Exception as e:
                logger.warning(f"同步模式回写会话状态失败: {e}")
            finally:
                if pg is not None:
                    try:
                        pg.close()
                    except Exception:
                        pass

        # 构建响应
        return MarketInsightResponse(
            session_id=session_id,
            status=WorkflowStatus.COMPLETED,
            report=result.get("synthesized_report", ""),
            report_html_url=report_html_url,
            evidence_pack=result.get("evidence_pack"),
            memory_snapshot=result.get("memory_snapshot"),
            agent_results=[
                {
                    "agent_name": r.agent_name,
                    "content": r.content,
                    "sources": r.sources,
                    "duration_ms": r.duration_ms,
                }
                for r in result.get("agent_results", [])
            ],
            debate_summary={
                "total_exchanges": len(result.get("debate_exchanges", [])),
                "rounds": result.get("current_debate_round", 0),
            },
            created_at=datetime.now(),
        )

    except GraphExecutionError as e:
        logger.error(f"工作流执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"未知错误: {e}")
        raise HTTPException(status_code=500, detail=f"系统错误: {str(e)}")


# ============================================
# 状态查询端点
# ============================================


@router.get("/status/{session_id}")
async def get_workflow_status(session_id: str):
    """
    查询工作流状态

    用于轮询模式或断线重连
    """
    if not pg_is_configured():
        return {
            "session_id": session_id,
            "status": "unknown",
            "message": "数据库未配置，状态查询不可用",
        }

    pg = create_pg_client()
    try:
        try:
            session_row = pg.get_session_row(session_id)
        except Exception as e:
            logger.error(f"状态查询失败 session={session_id}: {e}")
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

        report_path = get_report_file_path(session_id)
        if not report_path.exists() and session_row.get("synthesized_report"):
            try:
                write_html_report(
                    session_id=session_id,
                    report_markdown=session_row.get("synthesized_report") or "",
                    profile=session_row.get("profile") or {},
                )
            except Exception as e:
                logger.warning(f"按需生成 HTML 报告失败: {e}")

        if report_path.exists():
            session_row["report_html_url"] = (
                f"/api/v2/market-insight/report/{session_id}.html"
            )

        agent_results = pg.list_agent_results(session_id)
        debate_exchanges = pg.list_debate_exchanges(session_id)
        workflow_events = pg.list_workflow_events(session_id, limit=200)
        tool_invocations = pg.list_tool_invocations(session_id)
        tool_metrics = pg.aggregate_tool_metrics(session_id)

        # Phase 3：对历史会话按需回补 Evidence Pack / 记忆快照。
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
                except Exception as e:
                    logger.warning(f"按需回补 Evidence Pack 失败: {e}")

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
                except Exception as e:
                    logger.warning(f"按需回补记忆快照失败: {e}")

        if update_fields:
            try:
                pg.update_session_fields(session_id, update_fields)
            except Exception as e:
                logger.warning(f"回写 Phase 3 结构化结果失败: {e}")

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
        if synthesized_report and session_status in (
            "completed",
            "failed",
            "cancelled",
        ):
            try:
                write_html_report(
                    session_id=session_id,
                    report_markdown=synthesized_report,
                    profile=profile,
                    chart_bundle=report_charts,
                )
                session_row["report_html_url"] = (
                    f"/api/v2/market-insight/report/{session_id}.html"
                )
            except Exception as e:
                logger.warning(f"写入图表增强 HTML 报告失败: {e}")

        if session_status in ("completed", "failed", "cancelled"):
            try:
                append_rehearsal_metric(
                    {
                        "session_id": session_id,
                        "status": session_status,
                        "phase": session_row.get("phase"),
                        "profile": session_row.get("profile")
                        if isinstance(session_row.get("profile"), dict)
                        else {},
                        "demo_metrics": demo_metrics,
                    }
                )
            except Exception as e:
                logger.warning(f"写入 Phase 5 彩排日志失败: {e}")

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


@router.get("/sessions")
async def list_history_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
):
    """读取历史会话摘要（Phase 5 最小可演示版）。"""
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
        raw_rows = pg.list_sessions_summary(
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


# ============================================
# HTML 报告端点
# ============================================


@router.get("/report/{session_id}.html")
async def get_html_report(session_id: str, download: bool = False):
    """获取会话对应的 HTML 报告文件。"""
    report_path = get_report_file_path(session_id)

    if pg_is_configured():
        try:
            status_payload_raw = await get_workflow_status(session_id)
            status_payload = (
                cast(dict[str, Any], status_payload_raw)
                if isinstance(status_payload_raw, dict)
                else {}
            )
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
                write_html_report(
                    session_id=session_id,
                    report_markdown=session_row.get("synthesized_report") or "",
                    profile=session_row.get("profile")
                    if isinstance(session_row.get("profile"), dict)
                    else {},
                    chart_bundle=chart_bundle,
                )
        except Exception as e:
            logger.warning(f"按需刷新 HTML 报告失败: {e}")

    if not report_path.exists():
        raise HTTPException(status_code=404, detail="HTML 报告不存在")

    if download:
        return FileResponse(
            path=report_path,
            media_type="text/html",
            filename=f"weaveai-report-{session_id}.html",
        )

    return HTMLResponse(content=report_path.read_text(encoding="utf-8"))


@router.get("/export/{session_id}.zip")
async def export_roadshow_package(session_id: str):
    """导出 Phase 5 一键路演包（ZIP）。"""
    status_payload = await get_workflow_status(session_id)

    if status_payload.get("status") == "unknown":
        raise HTTPException(status_code=503, detail="数据库未配置，无法导出路演包")

    if status_payload.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="会话不存在")

    session_row = status_payload.get("session")
    if not isinstance(session_row, dict):
        raise HTTPException(status_code=404, detail="会话不存在")

    report_markdown = str(session_row.get("synthesized_report") or "").strip()
    if not report_markdown:
        raise HTTPException(status_code=409, detail="会话尚未生成可导出报告")

    report_path = get_report_file_path(session_id)
    if not report_path.exists():
        try:
            write_html_report(
                session_id=session_id,
                report_markdown=report_markdown,
                profile=session_row.get("profile")
                if isinstance(session_row.get("profile"), dict)
                else {},
            )
        except Exception as e:
            logger.error(f"导出路演包时生成 HTML 报告失败: {e}")
            raise HTTPException(status_code=500, detail="生成 HTML 报告失败")

    if not report_path.exists():
        raise HTTPException(status_code=500, detail="HTML 报告不存在，无法导出路演包")

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
    raw_demo_metrics = status_payload.get("demo_metrics")
    demo_metrics: dict[str, Any] = (
        cast(dict[str, Any], raw_demo_metrics)
        if isinstance(raw_demo_metrics, dict)
        else {}
    )
    raw_tool_metrics = status_payload.get("tool_metrics")
    tool_metrics: dict[str, Any] = (
        cast(dict[str, Any], raw_tool_metrics)
        if isinstance(raw_tool_metrics, dict)
        else {}
    )
    raw_workflow_events = status_payload.get("workflow_events")
    workflow_events: list[dict[str, Any]] = (
        [
            cast(dict[str, Any], row)
            for row in raw_workflow_events
            if isinstance(row, dict)
        ]
        if isinstance(raw_workflow_events, list)
        else []
    )
    raw_report_charts = status_payload.get("report_charts")
    report_charts: dict[str, Any] = (
        cast(dict[str, Any], raw_report_charts)
        if isinstance(raw_report_charts, dict)
        else {}
    )

    try:
        write_html_report(
            session_id=session_id,
            report_markdown=report_markdown,
            profile=session_row.get("profile")
            if isinstance(session_row.get("profile"), dict)
            else {},
            chart_bundle=report_charts,
        )
    except Exception as e:
        logger.warning(f"导出路演包时写入图表增强 HTML 失败: {e}")
        report_path = get_report_file_path(session_id)

    try:
        zip_path = write_roadshow_zip(
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出路演包失败: {e}")
        raise HTTPException(status_code=500, detail="导出路演包失败")

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"weaveai-roadshow-{session_id}.zip",
    )


# ============================================
# 健康检查
# ============================================


@router.get("/health")
async def health_check():
    """v2 API 健康检查"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "features": {
            "multi_agent": True,
            "debate": True,
            "streaming": True,
        },
    }
