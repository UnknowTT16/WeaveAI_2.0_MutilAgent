"""Phase 5 报告图表增强：构建 Vega-Lite 图表配置。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _overview_chart(demo_metrics: dict[str, Any]) -> dict[str, Any]:
    total_agents = max(1, _to_int(demo_metrics.get("total_agents"), 0))
    completed_agents = max(0, _to_int(demo_metrics.get("completed_agents"), 0))
    completion_rate = min(100.0, max(0.0, completed_agents * 100.0 / total_agents))

    stability_score = min(
        100.0, max(0.0, _to_float(demo_metrics.get("stability_score"), 0.0))
    )
    evidence_coverage = min(
        100.0,
        max(0.0, _to_float(demo_metrics.get("evidence_coverage_rate"), 0.0) * 100.0),
    )

    values = [
        {"metric": "稳定性评分", "value": round(stability_score, 2)},
        {"metric": "证据覆盖率", "value": round(evidence_coverage, 2)},
        {"metric": "完成率", "value": round(completion_rate, 2)},
    ]

    return {
        "id": "overview_quality",
        "title": "稳定性与证据概览",
        "description": "用于快速评估会话质量，数值越高越好。",
        "fallback_text": "若图表无法渲染，请关注稳定性评分、证据覆盖率与完成率三项指标。",
        "spec": {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "description": "会话质量概览",
            "width": "container",
            "height": 220,
            "data": {"values": values},
            "mark": {"type": "bar", "cornerRadiusEnd": 6},
            "encoding": {
                "y": {
                    "field": "metric",
                    "type": "nominal",
                    "sort": ["稳定性评分", "证据覆盖率", "完成率"],
                    "axis": {"title": None, "labelFontSize": 12},
                },
                "x": {
                    "field": "value",
                    "type": "quantitative",
                    "scale": {"domain": [0, 100]},
                    "axis": {"title": "分值（%）", "tickCount": 6},
                },
                "color": {
                    "field": "metric",
                    "type": "nominal",
                    "scale": {
                        "domain": ["稳定性评分", "证据覆盖率", "完成率"],
                        "range": ["#2563eb", "#10b981", "#8b5cf6"],
                    },
                    "legend": None,
                },
                "tooltip": [
                    {"field": "metric", "title": "指标"},
                    {"field": "value", "title": "数值", "format": ".2f"},
                ],
            },
            "config": {"view": {"stroke": "#e2e8f0"}},
        },
    }


def _tool_agent_chart(tool_metrics: dict[str, Any]) -> Optional[dict[str, Any]]:
    by_agent = tool_metrics.get("by_agent") if isinstance(tool_metrics, dict) else {}
    if not isinstance(by_agent, dict) or not by_agent:
        return None

    rows: list[dict[str, Any]] = []
    for agent_name, metric in by_agent.items():
        if not isinstance(metric, dict):
            continue
        calls = max(0, _to_int(metric.get("total_calls"), 0))
        if calls <= 0:
            continue
        rows.append(
            {
                "agent": str(agent_name),
                "calls": calls,
                "cost_usd": round(
                    max(0.0, _to_float(metric.get("total_estimated_cost_usd"), 0.0)), 6
                ),
                "error_rate": round(
                    max(0.0, _to_float(metric.get("error_rate"), 0.0) * 100.0), 2
                ),
            }
        )

    if not rows:
        return None

    rows.sort(key=lambda item: item["calls"], reverse=True)

    return {
        "id": "agent_tool_calls",
        "title": "Agent 工具调用分布",
        "description": "展示每个 Agent 的工具调用量，并附带成本与错误率。",
        "fallback_text": "若图表无法渲染，请重点查看高调用 Agent 的成本与错误率。",
        "spec": {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "description": "Agent 工具调用分布",
            "width": "container",
            "height": 260,
            "data": {"values": rows},
            "mark": {"type": "bar", "cornerRadiusEnd": 4},
            "encoding": {
                "x": {
                    "field": "agent",
                    "type": "nominal",
                    "sort": "-y",
                    "axis": {"title": None, "labelAngle": -20},
                },
                "y": {
                    "field": "calls",
                    "type": "quantitative",
                    "axis": {"title": "工具调用次数"},
                },
                "color": {
                    "field": "cost_usd",
                    "type": "quantitative",
                    "scale": {"scheme": "blues"},
                    "legend": {"title": "估算成本 (USD)"},
                },
                "tooltip": [
                    {"field": "agent", "title": "Agent"},
                    {"field": "calls", "title": "调用次数"},
                    {"field": "cost_usd", "title": "估算成本", "format": ".6f"},
                    {"field": "error_rate", "title": "错误率(%)", "format": ".2f"},
                ],
            },
            "config": {"view": {"stroke": "#e2e8f0"}},
        },
    }


def _degrade_breakdown_chart(demo_metrics: dict[str, Any]) -> dict[str, Any]:
    breakdown = (
        demo_metrics.get("degrade_breakdown")
        if isinstance(demo_metrics.get("degrade_breakdown"), dict)
        else {}
    )

    values = [
        {
            "category": "Agent 降级/跳过",
            "count": max(0, _to_int(breakdown.get("agent_degraded_or_skipped"), 0)),
        },
        {
            "category": "护栏触发",
            "count": max(0, _to_int(breakdown.get("guardrail_triggered"), 0)),
        },
        {
            "category": "并发降级",
            "count": max(
                0,
                _to_int(breakdown.get("adaptive_concurrency_degraded"), 0),
            ),
        },
    ]

    return {
        "id": "degrade_breakdown",
        "title": "降级类型分解",
        "description": "用于解释稳定性评分中的降级来源。",
        "fallback_text": "若图表无法渲染，可直接查看降级分解明细和重试次数。",
        "spec": {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "description": "降级类型分解",
            "width": "container",
            "height": 220,
            "data": {"values": values},
            "mark": {"type": "arc", "innerRadius": 55},
            "encoding": {
                "theta": {"field": "count", "type": "quantitative"},
                "color": {
                    "field": "category",
                    "type": "nominal",
                    "scale": {
                        "domain": ["Agent 降级/跳过", "护栏触发", "并发降级"],
                        "range": ["#f59e0b", "#ef4444", "#6366f1"],
                    },
                    "legend": {"title": None, "orient": "right"},
                },
                "tooltip": [
                    {"field": "category", "title": "降级类型"},
                    {"field": "count", "title": "次数"},
                ],
            },
            "config": {"view": {"stroke": "#e2e8f0"}},
        },
    }


def build_report_charts(
    *,
    session_id: str,
    profile: Optional[dict[str, Any]],
    demo_metrics: Optional[dict[str, Any]],
    tool_metrics: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """构建报告图表增强包（Vega-Lite）。"""
    demo_metrics = demo_metrics if isinstance(demo_metrics, dict) else {}
    tool_metrics = tool_metrics if isinstance(tool_metrics, dict) else {}

    charts: list[dict[str, Any]] = [_overview_chart(demo_metrics)]
    agent_chart = _tool_agent_chart(tool_metrics)
    if agent_chart:
        charts.append(agent_chart)
    charts.append(_degrade_breakdown_chart(demo_metrics))

    profile = profile if isinstance(profile, dict) else {}

    return {
        "session_id": session_id,
        "spec_version": "vega-lite/v6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile_summary": {
            "target_market": profile.get("target_market"),
            "supply_chain": profile.get("supply_chain"),
            "seller_type": profile.get("seller_type"),
        },
        "charts": charts,
    }
