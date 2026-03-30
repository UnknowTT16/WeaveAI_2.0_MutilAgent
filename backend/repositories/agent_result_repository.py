"""Agent 结果数据访问。"""

from __future__ import annotations

from typing import Any

from infrastructure.db.pg_client import PgClient


class AgentResultRepository:
    def __init__(self, pg: PgClient):
        self._pg = pg

    def upsert_agent_result(
        self,
        session_id: str,
        agent_name: str,
        fields: dict[str, Any],
    ) -> None:
        self._pg.upsert_agent_result(session_id, agent_name, fields)

    def list_agent_results(self, session_id: str) -> list[dict[str, Any]]:
        return self._pg.list_agent_results(session_id)
