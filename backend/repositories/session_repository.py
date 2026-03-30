"""会话数据访问。"""

from __future__ import annotations

from typing import Any, Optional

from infrastructure.db.pg_client import PgClient


class SessionRepository:
    """封装会话相关的 Postgres 操作。"""

    def __init__(self, pg: PgClient):
        self._pg = pg

    def create_session(
        self,
        session_id: str,
        profile: dict[str, Any],
        config: dict[str, Any],
    ) -> None:
        self._pg.create_session(session_id, profile, config)

    def update_session_fields(self, session_id: str, fields: dict[str, Any]) -> None:
        self._pg.update_session_fields(session_id, fields)

    def get_session_row(self, session_id: str) -> Optional[dict[str, Any]]:
        return self._pg.get_session_row(session_id)

    def list_sessions_summary(
        self,
        *,
        limit: int,
        offset: int,
        status: Optional[str],
    ) -> list[dict[str, Any]]:
        return self._pg.list_sessions_summary(limit=limit, offset=offset, status=status)
