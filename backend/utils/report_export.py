"""
HTML 报告导出工具

将综合报告 Markdown 转换为完整 HTML 文档并落盘。
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
import json
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


def _build_chart_section(chart_bundle: Optional[dict[str, Any]]) -> str:
    """构建图表增强区块（含失败回退）。"""
    if not isinstance(chart_bundle, dict):
        return ""

    charts = chart_bundle.get("charts")
    if not isinstance(charts, list):
        return ""

    valid_charts = [
        c for c in charts if isinstance(c, dict) and isinstance(c.get("spec"), dict)
    ]
    if not valid_charts:
        return ""

    cards: list[str] = []
    for idx, chart in enumerate(valid_charts, start=1):
        chart_id = _sanitize_session_id(str(chart.get("id") or f"chart_{idx}"))
        title = escape(str(chart.get("title") or f"关键图表 {idx}"))
        description = escape(str(chart.get("description") or ""))
        fallback_text = escape(
            str(chart.get("fallback_text") or "图表渲染失败，已回退到文本与原始配置。")
        )
        raw_spec = escape(
            json.dumps(chart.get("spec") or {}, ensure_ascii=False, indent=2)
        )

        cards.append(
            f"""
<article class=\"chart-card\" id=\"chart-card-{chart_id}\">
  <header>
    <h3>{title}</h3>
    <p>{description}</p>
  </header>
  <div class=\"chart-canvas\" id=\"weave-chart-{chart_id}\" aria-label=\"{title}\"></div>
  <div class=\"chart-fallback\" id=\"weave-chart-fallback-{chart_id}\">
    <div class=\"chart-fallback-text\">{fallback_text}</div>
    <div class=\"chart-error\" id=\"weave-chart-error-{chart_id}\">等待渲染...</div>
    <details>
      <summary>查看原始图表配置（Vega-Lite Spec）</summary>
      <pre id=\"weave-chart-raw-{chart_id}\">{raw_spec}</pre>
    </details>
  </div>
</article>
""".strip()
        )

    payload = {"charts": valid_charts}
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    render_script = """
<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
<script>
(function () {
  const payloadEl = document.getElementById('weaveai-chart-bundle');
  if (!payloadEl) return;

  let payload = {};
  try {
    payload = JSON.parse(payloadEl.textContent || '{}');
  } catch (err) {
    console.warn('chart payload parse failed', err);
  }

  const charts = Array.isArray(payload.charts) ? payload.charts : [];

  async function renderOne(chart) {
    const chartId = String(chart.id || '').replace(/[^a-zA-Z0-9_-]/g, '_');
    const mount = document.getElementById(`weave-chart-${chartId}`);
    const fallback = document.getElementById(`weave-chart-fallback-${chartId}`);
    const errorEl = document.getElementById(`weave-chart-error-${chartId}`);
    const rawEl = document.getElementById(`weave-chart-raw-${chartId}`);

    if (!mount || !fallback) return;

    if (rawEl) {
      try {
        rawEl.textContent = JSON.stringify(chart.spec || {}, null, 2);
      } catch (err) {
        rawEl.textContent = '{}';
      }
    }

    if (typeof window.vegaEmbed !== 'function') {
      if (errorEl) errorEl.textContent = 'Vega 引擎未加载，已回退文本模式。';
      fallback.style.display = 'block';
      return;
    }

    try {
      mount.innerHTML = '';
      await window.vegaEmbed(mount, chart.spec || {}, {
        actions: false,
        renderer: 'svg'
      });
      fallback.style.display = 'none';
    } catch (err) {
      const message = err && err.message ? err.message : String(err);
      if (errorEl) errorEl.textContent = `渲染失败：${message}`;
      fallback.style.display = 'block';
      mount.innerHTML = '';
    }
  }

  async function renderAll() {
    for (const chart of charts) {
      try {
        await renderOne(chart);
      } catch (err) {
        console.warn('chart render failed', err);
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderAll, { once: true });
  } else {
    renderAll();
  }
})();
</script>
""".strip()

    cards_html = "\n".join(cards)
    return f"""
<section class=\"charts-wrap\">
  <h2>关键图表增强（Vega-Lite）</h2>
  <p class=\"charts-note\">图表用于辅助理解，不替代正文结论。若渲染异常，将自动回退到文本与原始配置。</p>
  <div class=\"charts-grid\">
    {cards_html}
  </div>
</section>
<script type=\"application/json\" id=\"weaveai-chart-bundle\">{payload_json}</script>
{render_script}
""".strip()


def build_report_html(
    *,
    session_id: str,
    report_markdown: str,
    profile: Optional[dict[str, Any]] = None,
    chart_bundle: Optional[dict[str, Any]] = None,
) -> str:
    """构建完整 HTML 报告文档。"""
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_session_id = escape(session_id)
    body_html = convert_markdown_to_html(
        report_markdown or "# 市场洞察报告\n\n暂无内容"
    )
    profile_meta = _build_profile_meta(profile)
    chart_section = _build_chart_section(chart_bundle)

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
    .charts-wrap {{ padding: 18px 28px 8px 28px; border-bottom: 1px solid var(--line); }}
    .charts-wrap h2 {{ margin: 0 0 8px 0; font-size: 20px; color: #0b3b82; }}
    .charts-note {{ margin: 0 0 14px 0; color: var(--muted); font-size: 13px; }}
    .charts-grid {{ display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
    .chart-card {{ border: 1px solid var(--line); border-radius: 12px; padding: 12px; background: #fff; }}
    .chart-card h3 {{ margin: 0; font-size: 16px; color: #0f172a; }}
    .chart-card p {{ margin: 6px 0 10px 0; font-size: 13px; color: var(--muted); }}
    .chart-canvas {{ min-height: 220px; width: 100%; }}
    .chart-fallback {{ display: block; border: 1px dashed #94a3b8; border-radius: 10px; padding: 10px; background: #f8fafc; }}
    .chart-fallback-text {{ color: #0f172a; font-size: 13px; margin-bottom: 8px; }}
    .chart-error {{ color: #b91c1c; font-size: 12px; margin-bottom: 8px; }}
    .chart-fallback details {{ margin-top: 8px; }}
    .chart-fallback pre {{ max-height: 220px; overflow: auto; background: #0f172a; color: #e2e8f0; padding: 10px; border-radius: 8px; font-size: 11px; line-height: 1.5; }}
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
      {chart_section}
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
    chart_bundle: Optional[dict[str, Any]] = None,
) -> Path:
    """写入 HTML 报告并返回文件路径。"""
    report_dir = get_reports_dir()
    report_dir.mkdir(parents=True, exist_ok=True)

    report_path = get_report_file_path(session_id)
    html_text = build_report_html(
        session_id=session_id,
        report_markdown=report_markdown,
        profile=profile,
        chart_bundle=chart_bundle,
    )
    report_path.write_text(html_text, encoding="utf-8")
    return report_path
