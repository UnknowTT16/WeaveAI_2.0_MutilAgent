"""
Phase 3 轻量记忆快照构建器

目标：
- 以 session 为粒度生成可回补的“关键实体 + 结论摘要 + 风险/行动项”
- 不依赖额外图数据库，便于比赛现场快速恢复上下文
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import re


def _to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    if hasattr(row, "model_dump"):
        try:
            return row.model_dump()  # type: ignore[call-arg]
        except Exception:
            pass
    if hasattr(row, "to_dict"):
        try:
            return row.to_dict()  # type: ignore[call-arg]
        except Exception:
            pass

    data: dict[str, Any] = {}
    for key in dir(row):
        if key.startswith("_"):
            continue
        try:
            value = getattr(row, key)
        except Exception:
            continue
        if callable(value):
            continue
        data[key] = value
    return data


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip(text: Any, limit: int = 180) -> str:
    raw = str(text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)] + "…"


def _extract_markdown_items(markdown_text: str, limit: int = 6) -> list[str]:
    """从 Markdown 文本中抽取列表项，用于行动项/风险项摘要。"""
    items: list[str] = []
    if not markdown_text:
        return items

    pattern = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.+)$")
    for line in markdown_text.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        value = _clip(match.group(1), 120)
        if value:
            items.append(value)
        if len(items) >= limit:
            break
    return items


def _extract_keywords(content: str) -> list[str]:
    """提取轻量关键词（规则法，避免引入重依赖）。"""
    if not content:
        return []
    separators = r"[，。；、,\.\s/\|\-_:：()\[\]{}]+"
    tokens = [t.strip() for t in re.split(separators, content) if len(t.strip()) >= 3]
    top: list[str] = []
    seen = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        top.append(token)
        if len(top) >= 5:
            break
    return top


def build_memory_snapshot(
    *,
    session_id: str,
    profile: Optional[dict[str, Any]],
    agent_results: list[Any],
    debate_exchanges: list[Any],
    final_report: str,
    generated_at: Optional[str] = None,
) -> dict[str, Any]:
    """
    构建 session 级轻量记忆快照。
    """
    generated_at = generated_at or _now_iso()
    profile = profile or {}

    agent_rows = [_to_dict(r) for r in agent_results or []]
    debate_rows = [_to_dict(r) for r in debate_exchanges or []]

    agent_highlights = []
    for row in agent_rows:
        content = str(row.get("content") or "")
        agent_highlights.append(
            {
                "agent_name": row.get("agent_name"),
                "status": row.get("status") or "unknown",
                "confidence": row.get("confidence"),
                "summary": _clip(content, 180),
                "keywords": _extract_keywords(content),
            }
        )

    revised_count = sum(1 for row in debate_rows if bool(row.get("revised")))
    debate_focus = [
        {
            "round_number": row.get("round_number"),
            "debate_type": row.get("debate_type"),
            "challenger": row.get("challenger"),
            "responder": row.get("responder"),
            "revised": bool(row.get("revised")),
        }
        for row in debate_rows
    ]

    action_items = _extract_markdown_items(final_report, limit=6)
    risk_items = [
        item
        for item in action_items
        if any(k in item.lower() for k in ("风险", "risk", "合规", "限制", "约束", "挑战"))
    ][:4]

    return {
        "version": "phase3.memory.v1",
        "session_id": session_id,
        "generated_at": generated_at,
        "entities": {
            "target_market": profile.get("target_market"),
            "supply_chain": profile.get("supply_chain"),
            "seller_type": profile.get("seller_type"),
            "price_range": {
                "min_price": profile.get("min_price"),
                "max_price": profile.get("max_price"),
            },
        },
        "summary": _clip(final_report, 260),
        "agent_highlights": agent_highlights,
        "debate_focus": debate_focus,
        "signals": {
            "debate_count": len(debate_rows),
            "revised_count": revised_count,
            "agent_count": len(agent_rows),
        },
        "action_items": action_items,
        "risk_items": risk_items,
    }

