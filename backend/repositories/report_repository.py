"""报告文件访问。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from infrastructure.exports.report_export import get_report_file_path, write_html_report


class ReportRepository:
    def get_report_file_path(self, session_id: str) -> Path:
        return get_report_file_path(session_id)

    def write_html_report(
        self,
        *,
        session_id: str,
        report_markdown: str,
        profile: dict[str, Any],
        chart_bundle: Optional[dict[str, Any]] = None,
    ) -> Path:
        return write_html_report(
            session_id=session_id,
            report_markdown=report_markdown,
            profile=profile,
            chart_bundle=chart_bundle,
        )
