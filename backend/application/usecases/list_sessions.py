"""历史会话列表用例。"""

from typing import Any, Optional

from application.services.market_insight_service import list_history_sessions_payload


async def list_sessions(
    *,
    limit: int,
    offset: int,
    status: Optional[str],
) -> dict[str, Any]:
    return await list_history_sessions_payload(
        limit=limit,
        offset=offset,
        status=status,
    )
