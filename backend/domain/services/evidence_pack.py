"""
Phase 3 证据包构建器

目标：
- 将会话中的关键结论、来源与辩论修订信息整理为结构化证据包
- 支持从 dataclass / dict 两种输入形态构建
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def _to_dict(row: Any) -> dict[str, Any]:
    """将对象转换为 dict（兼容 dataclass、pydantic、普通对象）。"""
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


def _clip_text(text: Any, limit: int = 220) -> str:
    raw = str(text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)] + "…"


def _normalize_source_list(raw_sources: Any) -> list[str]:
    """标准化来源列表，输出唯一 URL/文本引用列表。"""
    if not raw_sources:
        return []

    source_list: list[str] = []
    if isinstance(raw_sources, list):
        iterable = raw_sources
    else:
        iterable = [raw_sources]

    for item in iterable:
        if isinstance(item, str):
            value = item.strip()
        elif isinstance(item, dict):
            value = str(
                item.get("url")
                or item.get("source")
                or item.get("title")
                or item.get("id")
                or ""
            ).strip()
        else:
            value = str(item).strip()
        if value:
            source_list.append(value)

    # 去重并保持原顺序
    deduped: list[str] = []
    seen = set()
    for src in source_list:
        if src in seen:
            continue
        seen.add(src)
        deduped.append(src)
    return deduped


def _normalize_confidence(value: Any) -> float:
    try:
        num = float(value)
    except Exception:
        return 0.6
    return max(0.0, min(1.0, round(num, 3)))


def _build_source_index(agent_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """
    构建全局来源索引。

    Returns:
        (sources, value_to_id)
    """
    sources: list[dict[str, Any]] = []
    value_to_id: dict[str, str] = {}

    for row in agent_rows:
        agent_name = str(row.get("agent_name") or "unknown")
        for src in _normalize_source_list(row.get("sources")):
            if src in value_to_id:
                continue
            source_id = f"S{len(sources) + 1:03d}"
            value_to_id[src] = source_id
            sources.append(
                {
                    "source_id": source_id,
                    "source": src,
                    "first_seen_in_agent": agent_name,
                }
            )

    return sources, value_to_id


def build_evidence_pack(
    *,
    session_id: str,
    profile: Optional[dict[str, Any]],
    agent_results: list[Any],
    debate_exchanges: list[Any],
    final_report: str,
    generated_at: Optional[str] = None,
) -> dict[str, Any]:
    """
    构建 Evidence Pack 结构化输出。

    该函数不会抛出业务异常，保证在降级场景仍可输出最小证据包。
    """
    generated_at = generated_at or _now_iso()
    profile = profile or {}

    agent_rows = [_to_dict(r) for r in agent_results or []]
    debate_rows = [_to_dict(r) for r in debate_exchanges or []]

    sources, source_id_map = _build_source_index(agent_rows)
    claims: list[dict[str, Any]] = []
    traceability: list[dict[str, Any]] = []

    for idx, row in enumerate(agent_rows, start=1):
        agent_name = str(row.get("agent_name") or f"agent_{idx}")
        content = row.get("content") or ""
        confidence = _normalize_confidence(row.get("confidence"))
        source_refs = [
            source_id_map[src]
            for src in _normalize_source_list(row.get("sources"))
            if src in source_id_map
        ]

        claim_id = f"C{idx:03d}"
        claim = {
            "claim_id": claim_id,
            "agent": agent_name,
            "summary": _clip_text(content, limit=240),
            "confidence": confidence,
            "source_refs": source_refs,
            "generated_at": generated_at,
        }
        claims.append(claim)
        traceability.append(
            {
                "claim_id": claim_id,
                "from_agent": agent_name,
                "source_refs": source_refs,
            }
        )

    debate_adjustments = []
    for row in debate_rows:
        debate_adjustments.append(
            {
                "round_number": row.get("round_number"),
                "debate_type": row.get("debate_type"),
                "challenger": row.get("challenger"),
                "responder": row.get("responder"),
                "revised": bool(row.get("revised")),
                "challenge_summary": _clip_text(row.get("challenge_content"), 140),
                "response_summary": _clip_text(row.get("response_content"), 140),
            }
        )

    return {
        "version": "phase3.v1",
        "session_id": session_id,
        "generated_at": generated_at,
        "profile": {
            "target_market": profile.get("target_market"),
            "supply_chain": profile.get("supply_chain"),
            "seller_type": profile.get("seller_type"),
            "min_price": profile.get("min_price"),
            "max_price": profile.get("max_price"),
        },
        "report_excerpt": _clip_text(final_report, limit=300),
        "claims": claims,
        "sources": sources,
        "debate_adjustments": debate_adjustments,
        "traceability": traceability,
        "stats": {
            "claims_count": len(claims),
            "sources_count": len(sources),
            "debate_count": len(debate_adjustments),
        },
    }

