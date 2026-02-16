"""
HTML 报告导出工具

将综合报告 Markdown 转换为完整 HTML 文档并落盘。
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
import re
from typing import Any, Optional

from .markdown import convert_markdown_to_html


_SAFE_SESSION_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _sanitize_session_id(session_id: str) -> str:
    """清理 session_id，避免非法文件名。"""
    if not session_id:
        return "unknown"
    return _SAFE_SESSION_RE.sub("_", session_id)


def get_reports_dir() -> Path:
    """获取 HTML 报告目录。"""
    backend_dir = Path(__file__).resolve().parent.parent
    return backend_dir / "artifacts" / "reports"


def get_report_file_path(session_id: str) -> Path:
    """根据 session_id 计算 HTML 报告路径。"""
    safe_session = _sanitize_session_id(session_id)
    return get_reports_dir() / f"{safe_session}.html"


def _build_profile_meta(profile: Optional[dict[str, Any]]) -> str:
    """构建报告元信息 HTML。"""
    if not profile:
        return ""

    target_market = profile.get("target_market") or "未提供"
    supply_chain = profile.get("supply_chain") or "未提供"
    seller_type = profile.get("seller_type") or "未提供"
    min_price = profile.get("min_price")
    max_price = profile.get("max_price")
    if min_price is None or max_price is None:
        price_range = "未提供"
    else:
        price_range = f"${min_price}-${max_price}"

    target_market = escape(str(target_market))
    supply_chain = escape(str(supply_chain))
    seller_type = escape(str(seller_type))
    price_range = escape(str(price_range))

    return f"""
<section class=\"meta\">
  <div><strong>目标市场：</strong>{target_market}</div>
  <div><strong>核心品类：</strong>{supply_chain}</div>
  <div><strong>卖家类型：</strong>{seller_type}</div>
  <div><strong>价格区间：</strong>{price_range}</div>
</section>
""".strip()


def build_report_html(
    *,
    session_id: str,
    report_markdown: str,
    profile: Optional[dict[str, Any]] = None,
) -> str:
    """构建完整 HTML 报告文档。"""
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_session_id = escape(session_id)
    body_html = convert_markdown_to_html(
        report_markdown or "# 市场洞察报告\n\n暂无内容"
    )
    profile_meta = _build_profile_meta(profile)

    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>WeaveAI 报告 - {safe_session_id}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f8fafc;
      --card: #ffffff;
      --text: #0f172a;
      --muted: #475569;
      --line: #e2e8f0;
      --accent: #2563eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: radial-gradient(circle at top right, #e2e8f0 0%, var(--bg) 55%);
      color: var(--text);
      line-height: 1.7;
    }}
    .wrap {{ max-width: 980px; margin: 40px auto; padding: 0 20px; }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: 0 14px 34px rgba(15, 23, 42, 0.08);
      overflow: hidden;
    }}
    .header {{
      padding: 24px 28px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(120deg, #eff6ff 0%, #f8fafc 100%);
    }}
    .header h1 {{ margin: 0 0 8px 0; font-size: 26px; }}
    .meta {{
      margin-top: 14px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 8px 14px;
      font-size: 14px;
      color: var(--muted);
    }}
    .content {{ padding: 26px 28px 34px 28px; }}
    .content h1, .content h2, .content h3 {{ color: #0b3b82; margin-top: 1.2em; }}
    .content h1 {{ font-size: 30px; }}
    .content h2 {{ font-size: 24px; }}
    .content h3 {{ font-size: 20px; }}
    .content table {{ width: 100%; border-collapse: collapse; margin: 1em 0; font-size: 14px; }}
    .content th, .content td {{ border: 1px solid #cbd5e1; padding: 10px; text-align: left; vertical-align: top; }}
    .content th {{ background: #f1f5f9; }}
    .content code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 6px; }}
    .content pre {{ background: #0f172a; color: #e2e8f0; padding: 14px; border-radius: 10px; overflow: auto; }}
    .footer {{
      border-top: 1px solid var(--line);
      padding: 14px 28px;
      color: var(--muted);
      font-size: 13px;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    a {{ color: var(--accent); }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <article class=\"card\">
      <header class=\"header\">
        <h1>WeaveAI 市场洞察报告</h1>
        <div>会话 ID：{safe_session_id}</div>
        {profile_meta}
      </header>
      <main class=\"content\">{body_html}</main>
      <footer class=\"footer\">
        <span>生成时间：{generated_at}</span>
        <span>由 WeaveAI 2.0 自动导出</span>
      </footer>
    </article>
  </div>
</body>
</html>
"""


def write_html_report(
    *,
    session_id: str,
    report_markdown: str,
    profile: Optional[dict[str, Any]] = None,
) -> Path:
    """写入 HTML 报告并返回文件路径。"""
    report_dir = get_reports_dir()
    report_dir.mkdir(parents=True, exist_ok=True)

    report_path = get_report_file_path(session_id)
    html_text = build_report_html(
        session_id=session_id,
        report_markdown=report_markdown,
        profile=profile,
    )
    report_path.write_text(html_text, encoding="utf-8")
    return report_path
