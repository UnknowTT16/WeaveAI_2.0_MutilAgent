"""工具调用数据访问。"""

from __future__ import annotations

from typing import Any

from infrastructure.db.pg_client import PgClient


class ToolInvocationRepository:
    def __init__(self, pg: PgClient):
        self._pg = pg

    def insert_tool_invocation(self, fields: dict[str, Any]) -> None:
        self._pg.insert_tool_invocation(fields)

    def list_tool_invocations(self, session_id: str) -> list[dict[str, Any]]:
        return self._pg.list_tool_invocations(session_id)

    def aggregate_tool_metrics(self, session_id: str) -> dict[str, Any]:
        return self._pg.aggregate_tool_metrics(session_id)
