"""Phase 5 路演包导出工具。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
from typing import Any, Optional, cast
from zipfile import ZIP_DEFLATED, ZipFile


_SAFE_SESSION_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _sanitize_session_id(session_id: str) -> str:
    if not session_id:
        return "unknown"
    return _SAFE_SESSION_RE.sub("_", session_id)


def get_roadshow_exports_dir() -> Path:
    backend_dir = Path(__file__).resolve().parent.parent
    return backend_dir / "artifacts" / "exports"


def get_roadshow_zip_path(session_id: str) -> Path:
    safe_session = _sanitize_session_id(session_id)
    return get_roadshow_exports_dir() / f"{safe_session}.zip"


def _to_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _format_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "0.0%"


def _clip_text(text: Any, limit: int = 220) -> str:
    raw = str(text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 3)] + "..."


def _extract_headline(report_markdown: str) -> str:
    for line in str(report_markdown or "").splitlines():
        content = line.strip()
        if not content:
            continue
        if content.startswith("#"):
            content = content.lstrip("#").strip()
        if content:
            return _clip_text(content, 220)
    return "暂无可提取摘要，请查看完整报告。"


def build_executive_summary_markdown(
    *,
    session_id: str,
    session_row: dict[str, Any],
    demo_metrics: Optional[dict[str, Any]],
    tool_metrics: Optional[dict[str, Any]],
    report_markdown: str,
) -> str:
    raw_profile = session_row.get("profile")
    profile: dict[str, Any] = (
        cast(dict[str, Any], raw_profile) if isinstance(raw_profile, dict) else {}
    )
    raw_tool_session = (
        tool_metrics.get("session") if isinstance(tool_metrics, dict) else None
    )
    session_metrics: dict[str, Any] = (
        cast(dict[str, Any], raw_tool_session)
        if isinstance(raw_tool_session, dict)
        else {}
    )
    demo_metrics_dict: dict[str, Any] = (
        cast(dict[str, Any], demo_metrics) if isinstance(demo_metrics, dict) else {}
    )

    target_market = profile.get("target_market") or "未提供"
    supply_chain = profile.get("supply_chain") or "未提供"
    seller_type = profile.get("seller_type") or "未提供"
    min_price = profile.get("min_price")
    max_price = profile.get("max_price")
    if min_price is None or max_price is None:
        price_range = "未提供"
    else:
        price_range = f"${min_price}-${max_price}"

    duration_ms = demo_metrics_dict.get("total_duration_ms")
    if isinstance(duration_ms, (int, float)) and duration_ms > 0:
        if duration_ms < 60000:
            duration_text = f"{duration_ms / 1000:.1f}s"
        else:
            duration_text = (
                f"{int(duration_ms // 60000)}m {int((duration_ms % 60000) // 1000)}s"
            )
    else:
        duration_text = "--"

    return "\n".join(
        [
            "# WeaveAI 路演执行摘要",
            "",
            f"- 会话 ID: `{session_id}`",
            f"- 导出时间: {datetime.now(timezone.utc).isoformat()}",
            f"- 会话状态: {session_row.get('status') or 'unknown'}",
            "",
            "## 画像信息",
            f"- 目标市场: {target_market}",
            f"- 核心品类: {supply_chain}",
            f"- 卖家类型: {seller_type}",
            f"- 价格区间: {price_range}",
            "",
            "## 关键指标",
            f"- 全程耗时: {duration_text}",
            f"- 稳定性评分: {demo_metrics_dict.get('stability_score', 0)} ({demo_metrics_dict.get('stability_level', 'unknown')})",
            f"- 证据覆盖率: {_format_percent(demo_metrics_dict.get('evidence_coverage_rate', 0))}",
            f"- 降级次数: {demo_metrics_dict.get('degrade_count', 0)}",
            f"- 重试次数: {demo_metrics_dict.get('retry_count', 0)}",
            f"- 工具总调用: {session_metrics.get('total_calls', 0)}",
            f"- 工具错误率: {_format_percent(session_metrics.get('error_rate', 0))}",
            "",
            "## 一句话结论",
            f"- {_extract_headline(report_markdown)}",
            "",
            "## 附件说明",
            "- `report.html`: 完整可视化报告",
            "- `evidence_pack.json`: 结论证据链与来源追溯",
            "- `memory_snapshot.json`: 会话级轻量记忆快照",
            "- `demo_metrics.json`: 路演关键指标",
            "- `tool_metrics.json`: 工具调用成本与稳定性统计",
            "- `report_charts.json`: 报告图表增强配置（Vega-Lite）",
            "- `workflow_timeline.json`: 关键事件时间线",
        ]
    )


def write_roadshow_zip(
    *,
    session_id: str,
    session_row: dict[str, Any],
    report_markdown: str,
    report_html_path: Path,
    evidence_pack: Optional[dict[str, Any]],
    memory_snapshot: Optional[dict[str, Any]],
    demo_metrics: Optional[dict[str, Any]],
    tool_metrics: Optional[dict[str, Any]],
    workflow_events: Optional[list[dict[str, Any]]],
    report_charts: Optional[dict[str, Any]],
) -> Path:
    export_dir = get_roadshow_exports_dir()
    export_dir.mkdir(parents=True, exist_ok=True)

    zip_path = get_roadshow_zip_path(session_id)
    safe_session = _sanitize_session_id(session_id)
    package_root = f"weaveai-roadshow-{safe_session}"

    executive_summary = build_executive_summary_markdown(
        session_id=session_id,
        session_row=session_row,
        demo_metrics=demo_metrics,
        tool_metrics=tool_metrics,
        report_markdown=report_markdown,
    )

    file_manifest: list[str] = []
    with ZipFile(zip_path, mode="w", compression=ZIP_DEFLATED) as zf:
        if report_html_path.exists():
            arcname = f"{package_root}/report.html"
            zf.write(report_html_path, arcname=arcname)
            file_manifest.append("report.html")

        zf.writestr(f"{package_root}/executive_summary.md", executive_summary)
        file_manifest.append("executive_summary.md")

        zf.writestr(
            f"{package_root}/session_snapshot.json",
            _to_json_text(session_row),
        )
        file_manifest.append("session_snapshot.json")

        zf.writestr(
            f"{package_root}/evidence_pack.json",
            _to_json_text(evidence_pack or {}),
        )
        file_manifest.append("evidence_pack.json")

        zf.writestr(
            f"{package_root}/memory_snapshot.json",
            _to_json_text(memory_snapshot or {}),
        )
        file_manifest.append("memory_snapshot.json")

        zf.writestr(
            f"{package_root}/demo_metrics.json",
            _to_json_text(demo_metrics or {}),
        )
        file_manifest.append("demo_metrics.json")

        zf.writestr(
            f"{package_root}/tool_metrics.json",
            _to_json_text(tool_metrics or {}),
        )
        file_manifest.append("tool_metrics.json")

        zf.writestr(
            f"{package_root}/report_charts.json",
            _to_json_text(report_charts or {}),
        )
        file_manifest.append("report_charts.json")

        zf.writestr(
            f"{package_root}/workflow_timeline.json",
            _to_json_text(workflow_events or []),
        )
        file_manifest.append("workflow_timeline.json")

        manifest = {
            "package": "weaveai_roadshow_zip",
            "version": "phase5.v1",
            "session_id": session_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "status": session_row.get("status"),
            "files": file_manifest,
        }
        zf.writestr(f"{package_root}/manifest.json", _to_json_text(manifest))
        file_manifest.append("manifest.json")

    return zip_path
