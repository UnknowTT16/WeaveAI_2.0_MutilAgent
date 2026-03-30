"""工具调用指标估算与聚合。"""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _to_text(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(payload)


def estimate_tokens(payload: Any) -> int:
    """使用中英混合启发式估算 token 数。"""
    text = _to_text(payload)
    if not text:
        return 0

    ascii_words = len(re.findall(r"[A-Za-z0-9_]+", text))
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    punct_chars = len(re.findall(r"[^\w\s\u4e00-\u9fff]", text))

    estimate = (ascii_words * 1.3) + (cjk_chars * 1.5) + (punct_chars * 0.3)
    if estimate <= 0:
        return 1
    return int(round(estimate))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _normalize_model_env_key(model_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", model_name).upper()


def _get_pricing(model_name: str) -> tuple[float, float]:
    """读取每 1k token 的输入/输出估算单价（美元）。"""
    default_input = _safe_float(
        os.getenv("TOOL_ESTIMATED_INPUT_PRICE_USD_PER_1K"), 0.0005
    )
    default_output = _safe_float(
        os.getenv("TOOL_ESTIMATED_OUTPUT_PRICE_USD_PER_1K"), 0.0020
    )

    normalized = _normalize_model_env_key(model_name)
    model_input = _safe_float(
        os.getenv(f"TOOL_ESTIMATED_PRICE_{normalized}_INPUT_USD_PER_1K"),
        default_input,
    )
    model_output = _safe_float(
        os.getenv(f"TOOL_ESTIMATED_PRICE_{normalized}_OUTPUT_USD_PER_1K"),
        default_output,
    )
    return model_input, model_output


def estimate_cost_usd(
    *,
    model_name: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
) -> float:
    input_price, output_price = _get_pricing(model_name)
    cost = (estimated_input_tokens / 1000.0) * input_price + (
        estimated_output_tokens / 1000.0
    ) * output_price
    return float(Decimal(cost).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def estimate_invocation_metrics(
    *, input_payload: Any, output_payload: Any, model_name: str
) -> dict[str, Any]:
    input_tokens = estimate_tokens(input_payload)
    output_tokens = estimate_tokens(output_payload)
    cost_usd = estimate_cost_usd(
        model_name=model_name,
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
    )
    return {
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_cost_usd": cost_usd,
        "cost_mode": "estimate",
    }


def aggregate_tool_metrics(invocations: list[dict[str, Any]]) -> dict[str, Any]:
    """聚合 session 与 agent 维度指标。"""

    def _calc(rows: list[dict[str, Any]]) -> dict[str, Any]:
        total_calls = len(rows)
        error_count = sum(
            1
            for row in rows
            if str(row.get("status") or "").lower() in ("error", "failed")
        )
        total_duration = sum(int(row.get("duration_ms") or 0) for row in rows)
        total_cost = sum(
            _safe_float(row.get("estimated_cost_usd"), 0.0) for row in rows
        )
        cache_hits = sum(1 for row in rows if bool(row.get("cache_hit")))

        avg_duration = (total_duration / total_calls) if total_calls else 0.0
        error_rate = (error_count / total_calls) if total_calls else 0.0
        cache_hit_rate = (cache_hits / total_calls) if total_calls else 0.0

        return {
            "total_calls": total_calls,
            "error_count": error_count,
            "error_rate": round(error_rate, 4),
            "avg_duration_ms": round(avg_duration, 2),
            "total_estimated_cost_usd": round(total_cost, 6),
            "cache_hit_count": cache_hits,
            "cache_hit_rate": round(cache_hit_rate, 4),
            "cost_mode": "estimate",
        }

    by_agent_raw: dict[str, list[dict[str, Any]]] = {}
    for row in invocations:
        agent_name = str(row.get("agent_name") or "unknown")
        by_agent_raw.setdefault(agent_name, []).append(row)

    by_agent = {agent: _calc(rows) for agent, rows in by_agent_raw.items()}

    return {
        "session": _calc(invocations),
        "by_agent": by_agent,
    }
