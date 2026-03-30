"""辩论交换数据访问。"""

from __future__ import annotations

from typing import Any

from infrastructure.db.pg_client import PgClient


class DebateRepository:
    def __init__(self, pg: PgClient):
        self._pg = pg

    def insert_debate_exchange(self, session_id: str, fields: dict[str, Any]) -> None:
        self._pg.insert_debate_exchange(session_id, fields)

    def list_debate_exchanges(self, session_id: str) -> list[dict[str, Any]]:
        return self._pg.list_debate_exchanges(session_id)
