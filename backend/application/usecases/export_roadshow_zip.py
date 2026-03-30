"""路演包导出用例。"""

from pathlib import Path

from application.services.market_insight_service import build_roadshow_package


async def export_roadshow_zip(session_id: str) -> Path:
    return await build_roadshow_package(session_id)
