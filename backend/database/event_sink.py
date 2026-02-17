# backend/database/event_sink.py
"""\
SSE 事件落库汇聚器（Phase 1）

目标：
- 从 v2 SSE 事件流中提取关键生命周期信息
- 以最小写入实现 Phase 1 可验收的落库闭环

设计约束：
- 不阻塞 SSE：写库通过后台队列完成
- 不写 chunk 事件到 workflow_events（但会在内存中拼接用于产出最终 content）
"""

from __future__ import annotations

import queue
import threading
import time
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Optional

from database.pg_client import PgClient, pg_is_configured, create_pg_client


logger = logging.getLogger(__name__)


_CHUNK_EVENTS = {
    "agent_chunk",
    "agent_thinking",
    "challenge_chunk",
    "respond_chunk",
    "followup_chunk",
}


@dataclass
class _AgentBuf:
    content: list[str]
    thinking: list[str]


@dataclass
class _ToolStartBuf:
    invocation_id: str
    tool_name: str
    agent_name: Optional[str]
    context: Optional[str]
    model_name: Optional[str]
    cache_hit: bool
    input_payload: dict[str, Any]
    started_at: datetime


class DbWriteWorker:
    def __init__(self, pg: PgClient):
        self._pg = pg
        self._q: queue.Queue[tuple[str, tuple[Any, ...]]] = queue.Queue(maxsize=2000)
        self._stop = threading.Event()
        self._t = threading.Thread(
            target=self._run, name="weaveai-db-writer", daemon=True
        )

    def start(self) -> None:
        self._t.start()

    def stop(self) -> None:
        # 先发送停止哨兵，确保队列里已入队的写操作按顺序处理完成
        try:
            self._q.put_nowait(("__stop__", tuple()))
        except Exception:
            pass
        try:
            self._t.join(timeout=3)
        except Exception:
            pass
        self._stop.set()
        try:
            self._pg.close()
        except Exception:
            pass

    def enqueue(self, kind: str, args: tuple[Any, ...]) -> None:
        if self._stop.is_set():
            return
        try:
            self._q.put_nowait((kind, args))
        except queue.Full:
            # Phase 1：队列满直接丢弃，避免阻塞 SSE
            logger.warning("DB 写入队列已满，丢弃事件")

    def _run(self) -> None:
        # 注意：不能以 _stop 作为循环条件，否则 stop() 先置位会导致队列未清空就退出
        while True:
            kind, args = self._q.get()
            if kind == "__stop__":
                return
            try:
                if kind == "create_session":
                    self._pg.create_session(*args)  # type: ignore[misc]
                elif kind == "update_session":
                    self._pg.update_session_fields(*args)  # type: ignore[misc]
                elif kind == "upsert_agent_result":
                    self._pg.upsert_agent_result(*args)  # type: ignore[misc]
                elif kind == "insert_debate":
                    self._pg.insert_debate_exchange(*args)  # type: ignore[misc]
                elif kind == "workflow_event":
                    self._pg.insert_workflow_event(*args)  # type: ignore[misc]
                elif kind == "insert_tool_invocation":
                    self._pg.insert_tool_invocation(*args)  # type: ignore[misc]
            except Exception as e:
                # Phase 1：写入失败不影响主流程
                logger.warning(f"DB 写入失败({kind}): {e}")
                # 简单退避，避免疯狂打日志
                time.sleep(0.05)


class SessionEventSink:
    """按 session 聚合 SSE 事件，并写入数据库。"""

    def __init__(
        self, session_id: str, profile: dict[str, Any], config: dict[str, Any]
    ):
        self.session_id = session_id
        self.profile = profile
        self.config = config

        self._enabled = pg_is_configured()
        self._worker: Optional[DbWriteWorker] = None

        # 运行期聚合缓存
        self._agent_bufs: dict[str, _AgentBuf] = {}
        self._debate_ctx: dict[str, Any] = {
            "current_round": None,
            "current_debate_type": None,
        }
        self._exchange_parts: dict[tuple[int, str, str], dict[str, Any]] = {}
        self._tool_starts: dict[str, _ToolStartBuf] = {}

        if self._enabled:
            try:
                pg = create_pg_client()
                self._worker = DbWriteWorker(pg)
                self._worker.start()
                # 预创建 session（幂等）
                self._worker.enqueue(
                    "create_session",
                    (self.session_id, self.profile, self.config),
                )
            except Exception as e:
                self._enabled = False
                logger.warning(f"DB Sink 初始化失败，将跳过落库: {e}")

    def close(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker = None

    def _log_workflow_event(self, event: dict[str, Any]) -> None:
        if not self._enabled or self._worker is None:
            return

        event_type = str(event.get("event") or "")
        if event_type in _CHUNK_EVENTS:
            return

        agent = event.get("agent") or event.get("from_agent") or None
        payload = dict(event)
        # payload 里常常有 content，这里保留，但不要写 chunk
        self._worker.enqueue(
            "workflow_event", (self.session_id, event_type, payload, agent)
        )

    def on_event(self, event: dict[str, Any]) -> None:
        """接收单条 SSE event（json 解析后的 dict）。"""

        if not isinstance(event, dict):
            return

        event_type = str(event.get("event") or "")

        # 先记录关键事件流水
        self._log_workflow_event(event)

        if not self._enabled or self._worker is None:
            return

        if event_type == "tool_start":
            invocation_id = str(event.get("invocation_id") or "")
            if not invocation_id:
                return
            input_payload = event.get("input")
            input_payload = input_payload if isinstance(input_payload, dict) else {}
            self._tool_starts[invocation_id] = _ToolStartBuf(
                invocation_id=invocation_id,
                tool_name=str(event.get("tool") or ""),
                agent_name=str(event.get("agent") or "") or None,
                context=str(event.get("context") or "") or None,
                model_name=str(event.get("model_name") or "") or None,
                cache_hit=bool(event.get("cache_hit")),
                input_payload=input_payload,
                started_at=self._parse_timestamp(
                    event.get("started_at") or event.get("timestamp")
                )
                or datetime.now(),
            )
            return

        if event_type in ("tool_end", "tool_error"):
            invocation_id = str(event.get("invocation_id") or "")
            if not invocation_id:
                return
            self._flush_tool_invocation(invocation_id, event)
            return

        if event_type == "guardrail_triggered":
            self._worker.enqueue(
                "update_session",
                (self.session_id, {"enable_websearch": False}),
            )
            return

        # === Orchestrator ===
        if event_type == "orchestrator_start":
            self._worker.enqueue(
                "update_session",
                (
                    self.session_id,
                    {
                        "status": "running",
                        "phase": "gather",
                        "current_debate_round": 0,
                        "profile": self.profile,
                        "target_market": self.profile.get("target_market"),
                        "supply_chain": self.profile.get("supply_chain"),
                        "seller_type": self.profile.get("seller_type"),
                        "min_price": self.profile.get("min_price"),
                        "max_price": self.profile.get("max_price"),
                        "debate_rounds": self.config.get("debate_rounds"),
                        "enable_followup": self.config.get("enable_followup"),
                        "enable_websearch": self.config.get("enable_websearch"),
                    },
                ),
            )
            return

        if event_type == "orchestrator_end":
            update_fields: dict[str, Any] = {
                "status": "completed",
                "phase": "complete",
                "synthesized_report": event.get("final_report"),
                "completed_at": datetime.now(),
            }
            if isinstance(event.get("evidence_pack"), dict):
                update_fields["evidence_pack"] = event.get("evidence_pack")
                update_fields["evidence_generated_at"] = datetime.now()
            if isinstance(event.get("memory_snapshot"), dict):
                update_fields["memory_snapshot"] = event.get("memory_snapshot")
                update_fields["memory_snapshot_generated_at"] = datetime.now()
            self._worker.enqueue(
                "update_session",
                (
                    self.session_id,
                    update_fields,
                ),
            )
            return

        if event_type == "error":
            self._worker.enqueue(
                "update_session",
                (
                    self.session_id,
                    {
                        "status": "failed",
                        "phase": "error",
                        "error_message": event.get("error"),
                    },
                ),
            )
            return

        # === Agent 生命周期 ===
        if event_type == "agent_start":
            agent = str(event.get("agent") or "")
            if not agent:
                return
            self._agent_bufs[agent] = _AgentBuf(content=[], thinking=[])
            self._worker.enqueue(
                "upsert_agent_result",
                (
                    self.session_id,
                    agent,
                    {
                        "status": "running",
                        "error_message": None,
                    },
                ),
            )
            return

        if event_type == "agent_chunk":
            agent = str(event.get("agent") or "")
            content = event.get("content")
            if agent and isinstance(content, str):
                buf = self._agent_bufs.setdefault(
                    agent, _AgentBuf(content=[], thinking=[])
                )
                buf.content.append(content)
            return

        if event_type == "agent_thinking":
            agent = str(event.get("agent") or "")
            content = event.get("content")
            if agent and isinstance(content, str):
                buf = self._agent_bufs.setdefault(
                    agent, _AgentBuf(content=[], thinking=[])
                )
                buf.thinking.append(content)
            return

        if event_type == "agent_end":
            agent = str(event.get("agent") or "")
            if not agent:
                return
            buf = self._agent_bufs.get(agent)
            content = "".join(buf.content) if buf else None
            thinking = "".join(buf.thinking) if buf and buf.thinking else None
            duration_ms = event.get("duration_ms")

            fields: dict[str, Any] = {
                "status": str(event.get("status") or "completed"),
                "duration_ms": int(duration_ms)
                if isinstance(duration_ms, int)
                else None,
                "content": content,
                "thinking": thinking,
                "completed_at": datetime.now(),
            }
            # 清理 None
            fields = {k: v for k, v in fields.items() if v is not None}

            self._worker.enqueue(
                "upsert_agent_result", (self.session_id, agent, fields)
            )
            return

        if event_type == "agent_error":
            agent = str(event.get("agent") or "")
            if not agent:
                return
            self._worker.enqueue(
                "upsert_agent_result",
                (
                    self.session_id,
                    agent,
                    {
                        "status": "failed",
                        "error_message": event.get("error"),
                        "completed_at": datetime.now(),
                    },
                ),
            )
            return

        # === Debate ===
        if event_type == "debate_round_start":
            rn = event.get("round_number")
            dt = event.get("debate_type")
            if isinstance(rn, int):
                self._debate_ctx["current_round"] = rn
            if isinstance(dt, str):
                self._debate_ctx["current_debate_type"] = dt
            # 更新 session phase
            phase = "debate"
            if dt == "peer_review":
                phase = "debate_peer"
            elif dt == "red_team":
                phase = "debate_redteam"
            self._worker.enqueue(
                "update_session",
                (
                    self.session_id,
                    {
                        "phase": phase,
                        "current_debate_round": int(rn) if isinstance(rn, int) else 0,
                    },
                ),
            )
            return

        if event_type in ("agent_challenge", "agent_respond", "agent_followup"):
            rn = event.get("round_number")
            if not isinstance(rn, int):
                return
            from_agent = str(event.get("from_agent") or "")
            to_agent = str(event.get("to_agent") or "")
            if not from_agent or not to_agent:
                return

            # challenge 的 key 以 challenger->responder 为准
            if event_type == "agent_challenge":
                key = (rn, from_agent, to_agent)
            elif event_type == "agent_respond":
                # respond 是 responder->challenger，需翻转回 challenger->responder
                key = (rn, to_agent, from_agent)
            else:
                # followup challenger->responder
                key = (rn, from_agent, to_agent)

            ex = self._exchange_parts.setdefault(
                key,
                {
                    "round_number": rn,
                    "challenger": key[1],
                    "responder": key[2],
                    "debate_type": self._debate_ctx.get("current_debate_type"),
                    "challenge_parts": [],
                    "response_parts": [],
                    "followup_parts": [],
                    "revised": False,
                },
            )

            # 兼容部分场景直接在基础事件上携带完整内容
            if event_type == "agent_challenge":
                c = event.get("challenge_content") or event.get("content")
                if isinstance(c, str) and c:
                    ex["challenge_parts"] = [c]
            elif event_type == "agent_respond":
                c = event.get("response_content") or event.get("content")
                if isinstance(c, str) and c:
                    ex["response_parts"] = [c]
                ex["revised"] = bool(event.get("revised", ex.get("revised", False)))
            else:
                c = event.get("followup_content") or event.get("content")
                if isinstance(c, str) and c:
                    ex["followup_parts"] = [c]
            return

        if event_type in (
            "agent_challenge_end",
            "agent_respond_end",
            "agent_followup_end",
        ):
            rn = event.get("round_number")
            if not isinstance(rn, int):
                return
            from_agent = str(event.get("from_agent") or "")
            to_agent = str(event.get("to_agent") or "")
            if not from_agent or not to_agent:
                return

            if event_type == "agent_challenge_end":
                key = (rn, from_agent, to_agent)
                ex = self._exchange_parts.setdefault(
                    key,
                    {
                        "round_number": rn,
                        "challenger": key[1],
                        "responder": key[2],
                        "debate_type": self._debate_ctx.get("current_debate_type"),
                        "challenge_parts": [],
                        "response_parts": [],
                        "followup_parts": [],
                        "revised": False,
                    },
                )
                c = event.get("challenge_content") or event.get("content")
                if isinstance(c, str):
                    ex["challenge_parts"] = [c]
                return

            if event_type == "agent_respond_end":
                key = (rn, to_agent, from_agent)  # challenger, responder
                ex = self._exchange_parts.setdefault(
                    key,
                    {
                        "round_number": rn,
                        "challenger": key[1],
                        "responder": key[2],
                        "debate_type": self._debate_ctx.get("current_debate_type"),
                        "challenge_parts": [],
                        "response_parts": [],
                        "followup_parts": [],
                        "revised": False,
                    },
                )
                c = event.get("response_content") or event.get("content")
                if isinstance(c, str):
                    ex["response_parts"] = [c]
                ex["revised"] = bool(event.get("revised", ex.get("revised", False)))
                # 如果没有启用 followup，则此处直接入库
                if not bool(self.config.get("enable_followup", True)):
                    self._flush_exchange(key)
                return

            # followup_end: challenger->responder
            key = (rn, from_agent, to_agent)
            ex = self._exchange_parts.setdefault(
                key,
                {
                    "round_number": rn,
                    "challenger": key[1],
                    "responder": key[2],
                    "debate_type": self._debate_ctx.get("current_debate_type"),
                    "challenge_parts": [],
                    "response_parts": [],
                    "followup_parts": [],
                    "revised": False,
                },
            )
            c = event.get("followup_content") or event.get("content")
            if isinstance(c, str):
                ex["followup_parts"] = [c]
            self._flush_exchange(key)
            return

        if event_type in ("challenge_chunk", "respond_chunk", "followup_chunk"):
            agent = str(event.get("agent") or "")
            content = event.get("content")
            rn = self._debate_ctx.get("current_round")
            if not isinstance(rn, int) or not isinstance(content, str) or not agent:
                return

            # 根据 chunk 类型尝试匹配 exchange
            for (round_number, challenger, responder), ex in list(
                self._exchange_parts.items()
            ):
                if round_number != rn:
                    continue
                if event_type == "challenge_chunk" and agent in (
                    challenger,
                    "debate_challenger",
                ):
                    ex["challenge_parts"].append(content)
                    break
                if event_type == "respond_chunk" and agent == responder:
                    ex["response_parts"].append(content)
                    break
                if event_type == "followup_chunk" and agent in (
                    challenger,
                    "debate_challenger",
                ):
                    ex["followup_parts"].append(content)
                    break
            return

        if event_type == "debate_round_end":
            return

    def _flush_exchange(self, key: tuple[int, str, str]) -> None:
        if not self._enabled or self._worker is None:
            return

        ex = self._exchange_parts.pop(key, None)
        if not ex:
            return

        challenge_content = "".join(ex.get("challenge_parts") or [])
        response_content = "".join(ex.get("response_parts") or [])
        followup_content = "".join(ex.get("followup_parts") or []) or None
        revised = (
            bool(ex.get("revised"))
            or ("修订" in response_content)
            or ("修改" in response_content)
        )

        self._worker.enqueue(
            "insert_debate",
            (
                self.session_id,
                {
                    "round_number": ex.get("round_number"),
                    "debate_type": ex.get("debate_type"),
                    "challenger": ex.get("challenger"),
                    "responder": ex.get("responder"),
                    "challenge_content": challenge_content,
                    "response_content": response_content,
                    "followup_content": followup_content,
                    "revised": revised,
                },
            ),
        )

    def _flush_tool_invocation(self, invocation_id: str, event: dict[str, Any]) -> None:
        if not self._enabled or self._worker is None:
            return

        start = self._tool_starts.pop(invocation_id, None)
        started_at = (
            start.started_at
            if start is not None
            else self._parse_timestamp(event.get("started_at")) or datetime.now()
        )
        finished_at = (
            self._parse_timestamp(event.get("finished_at") or event.get("timestamp"))
            or datetime.now()
        )

        duration_raw = event.get("duration_ms")
        if isinstance(duration_raw, int):
            duration_ms = duration_raw
        else:
            duration_ms = max(
                0,
                int((finished_at - started_at).total_seconds() * 1000),
            )

        input_payload: dict[str, Any]
        event_input = event.get("input")
        if isinstance(event_input, dict):
            input_payload = event_input
        elif start is not None:
            input_payload = start.input_payload
        else:
            input_payload = {}

        output_payload = (
            event.get("output") if isinstance(event.get("output"), dict) else {}
        )
        status = str(event.get("status") or "completed")
        if event.get("event") == "tool_error":
            status = "error"

        model_name = str(
            event.get("model_name") or (start.model_name if start else "") or ""
        )
        tool_name = str(event.get("tool") or (start.tool_name if start else "") or "")
        agent_name = str(
            event.get("agent") or (start.agent_name if start else "") or ""
        )
        context = str(event.get("context") or (start.context if start else "") or "")

        fields: dict[str, Any] = {
            "session_id": self.session_id,
            "invocation_id": invocation_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "input": input_payload,
            "output": output_payload,
            "error_message": event.get("error"),
            "context": context,
            "model_name": model_name,
            "cache_hit": bool(
                event.get("cache_hit")
                if event.get("cache_hit") is not None
                else (start.cache_hit if start else False)
            ),
            "estimated_input_tokens": self._parse_int(
                event.get("estimated_input_tokens")
            ),
            "estimated_output_tokens": self._parse_int(
                event.get("estimated_output_tokens")
            ),
            "estimated_cost_usd": self._parse_float(event.get("estimated_cost_usd")),
            "started_at": started_at,
            "finished_at": finished_at,
        }

        self._worker.enqueue("insert_tool_invocation", (fields,))

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str) or not value:
            return None
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except Exception:
            return None

    @staticmethod
    def _parse_int(value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _parse_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None


def create_session_event_sink(
    session_id: str, profile: dict[str, Any], config: dict[str, Any]
) -> SessionEventSink:
    return SessionEventSink(session_id=session_id, profile=profile, config=config)
