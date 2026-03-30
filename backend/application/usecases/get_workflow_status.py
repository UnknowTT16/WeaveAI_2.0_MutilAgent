"""状态查询用例。"""

from typing import Any

from application.services.market_insight_service import get_workflow_status_payload


async def get_workflow_status(session_id: str) -> dict[str, Any]:
    return await get_workflow_status_payload(session_id)
