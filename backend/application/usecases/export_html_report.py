"""HTML 报告导出用例。"""

from pathlib import Path

from application.services.market_insight_service import ensure_html_report_path


async def export_html_report(session_id: str) -> Path:
    return await ensure_html_report_path(session_id)
