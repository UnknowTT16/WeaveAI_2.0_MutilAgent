"""ToolRegistry Lite：统一工具调用生命周期与护栏联动。"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from tools.guardrail import ToolGuardrail
from tools.metrics import estimate_invocation_metrics


@dataclass
class InvocationState:
    session_id: str
    invocation_id: str
    tool_name: str
    agent_name: str
    context: Optional[str]
    model_name: str
    cache_hit: bool
    input_payload: dict[str, Any]
    started_at: datetime


class ToolRegistry:
    """统一发射 tool_start/tool_end/tool_error，并在末端执行护栏判定。"""

    def __init__(self, guardrail: ToolGuardrail):
        self._guardrail = guardrail
        self._lock = threading.Lock()
        self._active: dict[str, InvocationState] = {}

    def should_enable_websearch(self, *, session_id: str, requested: bool) -> bool:
        return bool(requested) and not self._guardrail.is_websearch_disabled(session_id)

    def begin_invocation(
        self,
        *,
        writer: Callable,
        session_id: str,
        tool_name: str,
        agent_name: str,
        model_name: str,
        input_payload: Optional[dict[str, Any]] = None,
        context: Optional[str] = None,
        cache_hit: bool = False,
    ) -> str:
        started_at = datetime.now(timezone.utc)
        invocation_id = str(uuid.uuid4())
        state = InvocationState(
            session_id=session_id,
            invocation_id=invocation_id,
            tool_name=tool_name,
            agent_name=agent_name,
            context=context,
            model_name=model_name,
            cache_hit=cache_hit,
            input_payload=input_payload or {},
            started_at=started_at,
        )

        with self._lock:
            self._active[invocation_id] = state

        writer(
            {
                "event": "tool_start",
                "invocation_id": invocation_id,
                "tool": tool_name,
                "agent": agent_name,
                "context": context,
                "model_name": model_name,
                "cache_hit": cache_hit,
                "input": state.input_payload,
                "started_at": started_at.isoformat(),
                "timestamp": started_at.isoformat(),
            }
        )
        return invocation_id

    def end_invocation(
        self,
        *,
        writer: Callable,
        invocation_id: str,
        output_payload: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        state = self._pop_or_fallback(invocation_id)
        finished_at = datetime.now(timezone.utc)
        duration_ms = max(
            0, int((finished_at - state.started_at).total_seconds() * 1000)
        )
        merged_output = dict(output_payload or {})
        if metadata:
            merged_output.setdefault("metadata", metadata)

        sources = self._extract_sources(metadata)
        if sources:
            merged_output.setdefault("sources", sources)
        if metadata and "sources_count" in metadata:
            merged_output.setdefault("sources_count", metadata.get("sources_count"))

        estimate = estimate_invocation_metrics(
            input_payload=state.input_payload,
            output_payload=merged_output,
            model_name=state.model_name,
        )

        payload = {
            "event": "tool_end",
            "invocation_id": state.invocation_id,
            "tool": state.tool_name,
            "agent": state.agent_name,
            "context": state.context,
            "model_name": state.model_name,
            "cache_hit": state.cache_hit,
            "input": state.input_payload,
            "output": merged_output,
            "sources_count": int((metadata or {}).get("sources_count") or len(sources)),
            "duration_ms": duration_ms,
            "started_at": state.started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "estimated_input_tokens": estimate["estimated_input_tokens"],
            "estimated_output_tokens": estimate["estimated_output_tokens"],
            "estimated_cost_usd": estimate["estimated_cost_usd"],
            "cost_mode": "estimate",
            "timestamp": finished_at.isoformat(),
        }
        writer(payload)

        guardrail_payload = self._apply_guardrail(
            writer=writer,
            session_id=state.session_id,
            status="completed",
            estimated_cost_usd=estimate["estimated_cost_usd"],
        )

        return {
            "invocation_id": state.invocation_id,
            "sources": sources,
            "guardrail_triggered": bool(guardrail_payload),
        }

    def error_invocation(
        self,
        *,
        writer: Callable,
        invocation_id: str,
        error_message: str,
        output_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        state = self._pop_or_fallback(invocation_id)
        finished_at = datetime.now(timezone.utc)
        duration_ms = max(
            0, int((finished_at - state.started_at).total_seconds() * 1000)
        )

        merged_output = dict(output_payload or {})
        merged_output.setdefault("error", error_message)

        estimate = estimate_invocation_metrics(
            input_payload=state.input_payload,
            output_payload=merged_output,
            model_name=state.model_name,
        )

        writer(
            {
                "event": "tool_error",
                "invocation_id": state.invocation_id,
                "tool": state.tool_name,
                "agent": state.agent_name,
                "context": state.context,
                "model_name": state.model_name,
                "cache_hit": state.cache_hit,
                "input": state.input_payload,
                "output": merged_output,
                "error": error_message,
                "duration_ms": duration_ms,
                "started_at": state.started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "estimated_input_tokens": estimate["estimated_input_tokens"],
                "estimated_output_tokens": estimate["estimated_output_tokens"],
                "estimated_cost_usd": estimate["estimated_cost_usd"],
                "cost_mode": "estimate",
                "timestamp": finished_at.isoformat(),
            }
        )

        guardrail_payload = self._apply_guardrail(
            writer=writer,
            session_id=state.session_id,
            status="error",
            estimated_cost_usd=estimate["estimated_cost_usd"],
        )

        return {
            "invocation_id": state.invocation_id,
            "guardrail_triggered": bool(guardrail_payload),
        }

    def _apply_guardrail(
        self,
        *,
        writer: Callable,
        session_id: str,
        status: str,
        estimated_cost_usd: float,
    ) -> Optional[dict[str, Any]]:
        self._guardrail.record_invocation(
            session_id=session_id,
            status=status,
            estimated_cost_usd=estimated_cost_usd,
        )
        triggered, reason, stats = self._guardrail.evaluate(session_id=session_id)
        if not triggered:
            return None
        if not self._guardrail.mark_triggered(session_id):
            return None

        payload = {
            "event": "guardrail_triggered",
            "session_id": session_id,
            "action": self._guardrail.action,
            "reason": reason,
            "stats": stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        writer(payload)
        return payload

    def _pop_or_fallback(self, invocation_id: str) -> InvocationState:
        with self._lock:
            state = self._active.pop(invocation_id, None)
        if state is not None:
            return state
        now = datetime.now(timezone.utc)
        return InvocationState(
            session_id="",
            invocation_id=invocation_id,
            tool_name="web_search",
            agent_name="unknown",
            context=None,
            model_name="unknown",
            cache_hit=False,
            input_payload={},
            started_at=now,
        )

    @staticmethod
    def _extract_sources(metadata: Optional[dict[str, Any]]) -> list[str]:
        if not isinstance(metadata, dict):
            return []
        raw = metadata.get("sources")
        if not isinstance(raw, list):
            return []
        sources: list[str] = []
        for item in raw:
            if isinstance(item, str) and item not in sources:
                sources.append(item)
        return sources
