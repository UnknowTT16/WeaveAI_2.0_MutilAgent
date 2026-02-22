"""
Phase 5 彩排脚本

用途：
- 按预置场景执行至少 3 轮完整演示
- 校验关键链路（status / 图表增强 / 导出路演包）
- 生成结果与问题清单，支撑 Phase 5 验收收尾
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import time
import uuid
from typing import Any
from zipfile import ZipFile

import httpx


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_profile(seed: int) -> dict[str, Any]:
    profiles = [
        {
            "target_market": "Germany",
            "supply_chain": "Consumer Electronics",
            "seller_type": "brand",
            "min_price": 30,
            "max_price": 90,
        },
        {
            "target_market": "France",
            "supply_chain": "Home Fitness",
            "seller_type": "trader",
            "min_price": 25,
            "max_price": 70,
        },
        {
            "target_market": "United Kingdom",
            "supply_chain": "Pet Supplies",
            "seller_type": "brand",
            "min_price": 15,
            "max_price": 55,
        },
    ]
    return profiles[seed % len(profiles)]


def _scenario_payload(round_idx: int, session_id: str) -> tuple[str, dict[str, Any]]:
    scenarios = [
        (
            "fast60",
            {
                "debate_rounds": 0,
                "enable_followup": False,
                "enable_websearch": False,
                "retry_max_attempts": 1,
                "retry_backoff_ms": 100,
                "degrade_mode": "partial",
            },
        ),
        (
            "standard3m",
            {
                "debate_rounds": 1,
                "enable_followup": True,
                "enable_websearch": False,
                "retry_max_attempts": 2,
                "retry_backoff_ms": 300,
                "degrade_mode": "partial",
            },
        ),
        (
            "deep",
            {
                "debate_rounds": 2,
                "enable_followup": True,
                "enable_websearch": False,
                "retry_max_attempts": 2,
                "retry_backoff_ms": 300,
                "degrade_mode": "partial",
            },
        ),
    ]
    name, config = scenarios[round_idx % len(scenarios)]
    payload = {
        "session_id": session_id,
        "profile": _build_profile(round_idx),
        **config,
    }
    return name, payload


def _has_report_charts(payload: dict[str, Any]) -> bool:
    charts = payload.get("report_charts")
    if not isinstance(charts, dict):
        return False
    rows = charts.get("charts")
    return isinstance(rows, list) and len(rows) >= 1


def _has_demo_metrics(payload: dict[str, Any]) -> bool:
    demo = payload.get("demo_metrics")
    if not isinstance(demo, dict):
        return False
    required = ["stability_score", "evidence_coverage_rate", "degrade_count"]
    return all(k in demo for k in required)


def _validate_export_zip(content: bytes) -> tuple[bool, list[str], list[str]]:
    required_suffixes = [
        "report.html",
        "executive_summary.md",
        "evidence_pack.json",
        "memory_snapshot.json",
        "demo_metrics.json",
        "tool_metrics.json",
        "report_charts.json",
        "workflow_timeline.json",
        "manifest.json",
    ]
    names: list[str] = []
    try:
        with ZipFile(io.BytesIO(content)) as zf:
            names = zf.namelist()
    except Exception:
        return False, [], required_suffixes

    missing: list[str] = []
    for suffix in required_suffixes:
        if not any(name.endswith(suffix) for name in names):
            missing.append(suffix)
    return len(missing) == 0, names, missing


def _run_stream_once(
    *,
    client: httpx.Client,
    stream_url: str,
    payload: dict[str, Any],
    timeout_sec: float,
) -> tuple[int | None, int, dict[str, Any] | None, str | None]:
    event_count = 0
    end_event: dict[str, Any] | None = None
    err: str | None = None
    http_code: int | None = None

    try:
        with client.stream(
            "POST", stream_url, json=payload, timeout=max(30.0, timeout_sec)
        ) as resp:
            http_code = resp.status_code
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8") if isinstance(line, bytes) else line
                if not text.startswith("data: "):
                    continue
                body = text[6:]
                if body == "[DONE]":
                    break
                try:
                    event = json.loads(body)
                except Exception:
                    continue
                if not isinstance(event, dict):
                    continue
                event_count += 1
                if event.get("event") == "orchestrator_end":
                    end_event = event
                    break
                if event.get("event") == "error":
                    err = str(event.get("error") or "stream error")
                    break
    except Exception as e:
        err = str(e)

    return http_code, event_count, end_event, err


def _poll_status_until_terminal(
    *,
    client: httpx.Client,
    status_url: str,
    timeout_sec: float,
) -> tuple[int | None, dict[str, Any]]:
    deadline = time.time() + max(15.0, timeout_sec)
    last_http: int | None = None
    last_payload: dict[str, Any] = {}
    while time.time() <= deadline:
        try:
            resp = client.get(status_url, timeout=30.0)
            last_http = resp.status_code
            if resp.status_code == 200:
                payload = resp.json() if resp.content else {}
                if isinstance(payload, dict):
                    last_payload = payload
                    session = payload.get("session")
                    if isinstance(session, dict):
                        status = str(session.get("status") or "").lower()
                        if status in {"completed", "failed", "cancelled"}:
                            return last_http, last_payload
            time.sleep(2.0)
        except Exception:
            time.sleep(2.0)
    return last_http, last_payload


def run_one_round(
    *,
    client: httpx.Client,
    api_base: str,
    round_idx: int,
    timeout_sec: float,
) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    scenario_name, payload = _scenario_payload(round_idx, session_id)
    started = time.time()

    record: dict[str, Any] = {
        "round": round_idx + 1,
        "scenario": scenario_name,
        "session_id": session_id,
        "started_at": _now_iso(),
        "generate_http": None,
        "status_http": None,
        "export_http": None,
        "history_http": None,
        "checks": {},
        "ok": False,
        "error": None,
    }

    try:
        stream_http, stream_events, stream_end_event, stream_err = _run_stream_once(
            client=client,
            stream_url=f"{api_base}/api/v2/market-insight/stream",
            payload=payload,
            timeout_sec=timeout_sec,
        )
        record["generate_http"] = stream_http
        record["stream_event_count"] = stream_events
        record["stream_end_event"] = isinstance(stream_end_event, dict)
        if stream_err:
            record["error"] = stream_err

        status_http, status_payload = _poll_status_until_terminal(
            client=client,
            status_url=f"{api_base}/api/v2/market-insight/status/{session_id}",
            timeout_sec=min(240.0, timeout_sec),
        )
        record["status_http"] = status_http
        if not isinstance(status_payload, dict):
            status_payload = {}

        session = (
            status_payload.get("session") if isinstance(status_payload, dict) else {}
        )
        if not isinstance(session, dict):
            session = {}

        session_status = str(session.get("status") or "").lower()
        report_html_url = session.get("report_html_url") or (
            f"/api/v2/market-insight/report/{session_id}.html"
        )
        report_html_abs = (
            report_html_url
            if str(report_html_url).startswith("http")
            else f"{api_base}{report_html_url}"
        )

        html_resp = client.get(report_html_abs, timeout=60.0)
        html_ok = html_resp.status_code == 200
        html_text = html_resp.text if html_ok else ""

        export_resp = client.get(
            f"{api_base}/api/v2/market-insight/export/{session_id}.zip",
            timeout=120.0,
        )
        record["export_http"] = export_resp.status_code
        export_ok = export_resp.status_code == 200
        zip_ok, zip_entries, zip_missing = _validate_export_zip(
            export_resp.content if export_ok else b""
        )

        history_resp = client.get(
            f"{api_base}/api/v2/market-insight/sessions?limit=20&offset=0",
            timeout=30.0,
        )
        record["history_http"] = history_resp.status_code
        history_ok = history_resp.status_code == 200
        in_history = False
        if history_ok:
            payload_obj = history_resp.json() if history_resp.content else {}
            rows = payload_obj.get("sessions") if isinstance(payload_obj, dict) else []
            if isinstance(rows, list):
                in_history = any(
                    isinstance(row, dict) and str(row.get("id")) == session_id
                    for row in rows
                )

        checks = {
            "stream_has_orchestrator_end": bool(record.get("stream_end_event")),
            "session_terminal": session_status in {"completed", "failed", "cancelled"},
            "status_has_demo_metrics": _has_demo_metrics(status_payload),
            "status_has_report_charts": _has_report_charts(status_payload),
            "html_contains_chart_bundle": html_ok
            and "weaveai-chart-bundle" in html_text,
            "export_ok": export_ok,
            "export_contains_required_files": zip_ok,
            "history_api_ok": history_ok,
            "history_contains_session": in_history,
        }
        record["checks"] = checks
        record["zip_entries"] = zip_entries
        record["zip_missing"] = zip_missing
        record["session_status"] = session_status
        record["ok"] = all(bool(v) for v in checks.values())
    except Exception as e:
        record["error"] = str(e)
        record["ok"] = False

    record["duration_ms"] = int((time.time() - started) * 1000)
    record["finished_at"] = _now_iso()
    return record


def build_issue_markdown(records: list[dict[str, Any]]) -> str:
    total = len(records)
    passed = sum(1 for row in records if row.get("ok"))
    failed = total - passed

    lines = [
        "# Phase 5 彩排问题清单",
        "",
        f"- 轮次总数: {total}",
        f"- 通过轮次: {passed}",
        f"- 未通过轮次: {failed}",
        f"- 生成时间: {_now_iso()}",
        "",
        "## 轮次摘要",
        "",
        "| 轮次 | 场景 | session_id | 结果 | 耗时(ms) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in records:
        lines.append(
            f"| {row.get('round')} | {row.get('scenario')} | `{row.get('session_id')}` | {'通过' if row.get('ok') else '失败'} | {row.get('duration_ms')} |"
        )

    lines.append("")
    lines.append("## 问题与修复闭环")
    lines.append("")

    open_issues: list[str] = []
    for row in records:
        if row.get("ok"):
            continue
        raw_checks = row.get("checks")
        checks: dict[str, Any] = raw_checks if isinstance(raw_checks, dict) else {}
        failed_checks = [k for k, v in checks.items() if not v]
        reason = row.get("error") or (
            ", ".join(failed_checks) if failed_checks else "未知异常"
        )
        open_issues.append(
            f"- [ ] 轮次 {row.get('round')}（{row.get('scenario')}）失败：{reason}"
        )

    if open_issues:
        lines.extend(open_issues)
        lines.extend(
            [
                "",
                "### 建议修复动作",
                "",
                "- 优先检查后端日志中对应 session_id 的异常栈与工具调用失败点。",
                "- 若失败集中在导出链路，先验证 `report.html` 与 `report_charts.json` 是否写入成功。",
                "- 若失败集中在历史会话展示，检查 `/sessions` 的分页/筛选参数与数据库连接稳定性。",
            ]
        )
    else:
        lines.extend(
            [
                "- [x] 三轮彩排全部通过，当前无阻塞性问题。",
                "- [x] 导出链路、图表增强、历史会话回放链路均验证通过。",
                "",
                "### 闭环结论",
                "",
                "- [x] 问题清单已清空，可进入 Phase 5 验收勾选与版本冻结。",
            ]
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 三轮彩排脚本")
    parser.add_argument(
        "--api-base",
        type=str,
        default="http://127.0.0.1:8000",
        help="后端 API 地址",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
        help="彩排轮次数（默认 3）",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=600.0,
        help="单轮 generate 超时秒数",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("../artifacts/phase5/rehearsal_results.jsonl"),
        help="彩排结果 jsonl 输出",
    )
    parser.add_argument(
        "--issues",
        type=Path,
        default=Path("../artifacts/phase5/rehearsal_issues.md"),
        help="问题清单 markdown 输出",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="追加写入结果，不覆盖已有文件",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="起始轮次索引（用于分批执行 3 轮彩排）",
    )
    args = parser.parse_args()

    rounds = max(1, int(args.rounds))
    start_index = max(0, int(args.start_index))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.issues.parent.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    if args.append and args.out.exists():
        for line in args.out.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
                if isinstance(row, dict):
                    records.append(row)
            except Exception:
                continue
    else:
        args.out.write_text("", encoding="utf-8")

    # trust_env=False 避免系统代理影响本地回环请求
    with httpx.Client(trust_env=False) as client:
        for idx in range(rounds):
            current_round_index = start_index + idx
            row = run_one_round(
                client=client,
                api_base=args.api_base.rstrip("/"),
                round_idx=current_round_index,
                timeout_sec=max(30.0, float(args.timeout_sec)),
            )
            records.append(row)
            with args.out.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")

            issues_text = build_issue_markdown(records)
            args.issues.write_text(issues_text, encoding="utf-8")

            print(
                f"[round={row.get('round')}] scenario={row.get('scenario')} "
                f"ok={row.get('ok')} session={row.get('session_id')} "
                f"status={row.get('session_status')} duration_ms={row.get('duration_ms')}"
            )

    issues_text = build_issue_markdown(records)
    args.issues.write_text(issues_text, encoding="utf-8")

    success = sum(1 for row in records if row.get("ok"))
    print(f"总轮次: {len(records)}")
    print(f"通过轮次: {success}")
    print(f"结果文件: {args.out}")
    print(f"问题清单: {args.issues}")


if __name__ == "__main__":
    main()
