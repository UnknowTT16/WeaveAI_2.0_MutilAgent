# backend/routers/v2/market_insight.py
"""
v2 市场洞察 API 端点

提供 SSE 流式接口，支持 Supervisor-Worker + 多轮辩论 架构
"""

from typing import Optional, Any
from datetime import datetime
import json
import logging
import asyncio
import uuid

from fastapi import APIRouter, HTTPException, Request
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market-insight", tags=["Market Insight v2"])


def _next_or_end(iterator) -> Optional[dict[str, Any]]:
    """在线程中安全获取下一条事件，避免 StopIteration 进入 Future。"""
    try:
        return next(iterator)
    except StopIteration:
        return None


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

    try:
        # 创建 Agent 工厂
        factory = agent_factory_for_graph()

        # 创建图引擎
        gen_debate_rounds = (
            request.debate_rounds
            if request.debate_rounds is not None
            else settings.default_debate_rounds
        )
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
            "user_profile": request.profile.model_dump() if request.profile else {},
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
        session_row = pg.get_session_row(session_id)
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

        # Phase 3：对历史会话按需回补 Evidence Pack / 记忆快照。
        update_fields: dict[str, Any] = {}
        profile = session_row.get("profile") if isinstance(session_row.get("profile"), dict) else {}
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

        return {
            "session": session_row,
            "agent_results": agent_results,
            "debate_exchanges": debate_exchanges,
            "workflow_events": workflow_events,
        }
    finally:
        try:
            pg.close()
        except Exception:
            pass


# ============================================
# HTML 报告端点
# ============================================


@router.get("/report/{session_id}.html")
async def get_html_report(session_id: str, download: bool = False):
    """获取会话对应的 HTML 报告文件。"""
    report_path = get_report_file_path(session_id)

    if not report_path.exists() and pg_is_configured():
        pg = create_pg_client()
        try:
            session_row = pg.get_session_row(session_id)
            if session_row and session_row.get("synthesized_report"):
                write_html_report(
                    session_id=session_id,
                    report_markdown=session_row.get("synthesized_report") or "",
                    profile=session_row.get("profile") or {},
                )
        finally:
            try:
                pg.close()
            except Exception:
                pass

    if not report_path.exists():
        raise HTTPException(status_code=404, detail="HTML 报告不存在")

    if download:
        return FileResponse(
            path=report_path,
            media_type="text/html",
            filename=f"weaveai-report-{session_id}.html",
        )

    return HTMLResponse(content=report_path.read_text(encoding="utf-8"))


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
