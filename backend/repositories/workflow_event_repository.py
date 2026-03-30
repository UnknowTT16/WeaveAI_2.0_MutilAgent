"""工作流事件数据访问。"""

from __future__ import annotations

from typing import Any

from infrastructure.db.pg_client import PgClient


class WorkflowEventRepository:
    def __init__(self, pg: PgClient):
        self._pg = pg

    def insert_workflow_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        agent_name: str | None = None,
    ) -> None:
        self._pg.insert_workflow_event(session_id, event_type, payload, agent_name)

    def list_workflow_events(
        self,
        session_id: str,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return self._pg.list_workflow_events(session_id, limit=limit)
