"""
Phase 3 回放脚本

用途：
- 批量回放样本请求（调用 /generate + /status）
- 校验 Evidence Pack / 轻量记忆快照是否可用
- 产出 jsonl 结果，便于比赛前稳定性复核
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid
from typing import Any

import httpx


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_payload(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"样本不是对象结构: {path}")
    return data


def _extract_status_snapshot(status_payload: dict[str, Any]) -> dict[str, Any]:
    session = status_payload.get("session") if isinstance(status_payload, dict) else {}
    if not isinstance(session, dict):
        session = {}

    evidence_pack = session.get("evidence_pack")
    memory_snapshot = session.get("memory_snapshot")
    has_evidence = isinstance(evidence_pack, dict)
    has_memory = isinstance(memory_snapshot, dict)

    claims_count = 0
    traceability_count = 0
    if has_evidence:
        claims = evidence_pack.get("claims")
        traceability = evidence_pack.get("traceability")
        claims_count = len(claims) if isinstance(claims, list) else 0
        traceability_count = len(traceability) if isinstance(traceability, list) else 0

    return {
        "session_status": session.get("status"),
        "phase": session.get("phase"),
        "has_evidence_pack": has_evidence,
        "has_memory_snapshot": has_memory,
        "claims_count": claims_count,
        "traceability_count": traceability_count,
    }


def run_one_sample(
    *,
    client: httpx.Client,
    api_base: str,
    sample_path: Path,
    timeout_sec: float,
) -> dict[str, Any]:
    payload = _load_payload(sample_path)
    session_id = str(payload.get("session_id") or uuid.uuid4())
    payload["session_id"] = session_id

    started = time.time()
    generate_url = f"{api_base}/api/v2/market-insight/generate"
    status_url = f"{api_base}/api/v2/market-insight/status/{session_id}"

    record: dict[str, Any] = {
        "sample": sample_path.name,
        "session_id": session_id,
        "started_at": _now_iso(),
        "ok": False,
        "generate_http": None,
        "status_http": None,
        "error": None,
    }

    try:
        gen_resp = client.post(generate_url, json=payload, timeout=timeout_sec)
        record["generate_http"] = gen_resp.status_code
        gen_resp.raise_for_status()

        status_resp = client.get(status_url, timeout=timeout_sec)
        record["status_http"] = status_resp.status_code
        status_resp.raise_for_status()
        status_payload = status_resp.json()

        summary = _extract_status_snapshot(status_payload)
        record.update(summary)
        record["ok"] = bool(
            summary["has_evidence_pack"]
            and summary["has_memory_snapshot"]
            and summary["claims_count"] >= 1
            and summary["traceability_count"] >= 1
        )
    except Exception as e:
        record["error"] = str(e)

    record["duration_ms"] = int((time.time() - started) * 1000)
    record["finished_at"] = _now_iso()
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 样本回放脚本")
    parser.add_argument(
        "--samples-dir",
        type=Path,
        default=Path("./scripts/samples/phase3"),
        help="样本目录（包含 *.json）",
    )
    parser.add_argument(
        "--api-base",
        type=str,
        default="http://127.0.0.1:8000",
        help="后端 API 地址",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("../artifacts/phase3/replay_results.jsonl"),
        help="输出 jsonl 文件路径",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=180.0,
        help="单个请求超时时间（秒）",
    )
    args = parser.parse_args()

    samples_dir: Path = args.samples_dir
    if not samples_dir.exists():
        raise FileNotFoundError(f"样本目录不存在: {samples_dir}")

    sample_files = sorted(samples_dir.glob("*.json"))
    if not sample_files:
        raise FileNotFoundError(f"未发现样本文件: {samples_dir}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []

    with httpx.Client() as client:
        for sample_path in sample_files:
            record = run_one_sample(
                client=client,
                api_base=args.api_base.rstrip("/"),
                sample_path=sample_path,
                timeout_sec=max(10.0, args.timeout_sec),
            )
            records.append(record)
            print(
                f"[{record['sample']}] ok={record['ok']} "
                f"generate={record.get('generate_http')} "
                f"status={record.get('status_http')} "
                f"duration_ms={record.get('duration_ms')}"
            )

    with args.out.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    total = len(records)
    success = sum(1 for r in records if r.get("ok"))
    failed = total - success
    print(f"总样本: {total}")
    print(f"通过: {success}")
    print(f"失败: {failed}")
    print(f"结果文件: {args.out}")


if __name__ == "__main__":
    main()
