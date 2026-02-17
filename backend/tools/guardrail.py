"""工具调用护栏：会话级成本与错误率限制。"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class SessionGuardrailStats:
    total_calls: int = 0
    error_calls: int = 0
    estimated_cost_usd: float = 0.0

    @property
    def error_rate(self) -> float:
        if self.total_calls <= 0:
            return 0.0
        return self.error_calls / self.total_calls


class ToolGuardrail:
    def __init__(
        self,
        *,
        max_estimated_cost_usd: float,
        max_error_rate: float,
        min_calls_for_error_rate: int,
        action: str,
    ):
        self.max_estimated_cost_usd = float(max_estimated_cost_usd)
        self.max_error_rate = float(max_error_rate)
        self.min_calls_for_error_rate = max(1, int(min_calls_for_error_rate))
        self.action = action

        self._lock = threading.Lock()
        self._session_stats: dict[str, SessionGuardrailStats] = {}
        self._disabled_sessions: set[str] = set()
        self._triggered_sessions: set[str] = set()

    def record_invocation(
        self,
        *,
        session_id: str,
        status: str,
        estimated_cost_usd: float,
    ) -> SessionGuardrailStats:
        with self._lock:
            stats = self._session_stats.setdefault(session_id, SessionGuardrailStats())
            stats.total_calls += 1
            if str(status).lower() in ("error", "failed"):
                stats.error_calls += 1
            stats.estimated_cost_usd += float(estimated_cost_usd or 0.0)
            return SessionGuardrailStats(
                total_calls=stats.total_calls,
                error_calls=stats.error_calls,
                estimated_cost_usd=stats.estimated_cost_usd,
            )

    def is_websearch_disabled(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._disabled_sessions

    def evaluate(self, *, session_id: str) -> tuple[bool, str, dict[str, Any]]:
        with self._lock:
            stats = self._session_stats.get(session_id, SessionGuardrailStats())

            cost_hit = stats.estimated_cost_usd > self.max_estimated_cost_usd
            error_rate_hit = (
                stats.total_calls >= self.min_calls_for_error_rate
                and stats.error_rate > self.max_error_rate
            )

            if not (cost_hit or error_rate_hit):
                return (
                    False,
                    "",
                    {
                        "total_calls": stats.total_calls,
                        "error_rate": round(stats.error_rate, 4),
                        "estimated_cost_usd": round(stats.estimated_cost_usd, 6),
                    },
                )

            if cost_hit:
                reason = "estimated_cost_exceeded"
            else:
                reason = "error_rate_exceeded"

            self._disabled_sessions.add(session_id)
            return (
                True,
                reason,
                {
                    "total_calls": stats.total_calls,
                    "error_rate": round(stats.error_rate, 4),
                    "estimated_cost_usd": round(stats.estimated_cost_usd, 6),
                },
            )

    def mark_triggered(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._triggered_sessions:
                return False
            self._triggered_sessions.add(session_id)
            return True
