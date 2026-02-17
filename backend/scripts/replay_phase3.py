"""
Phase 3 回放脚本

用途：
- 批量回放样本请求（优先走 /stream，必要时可切到 /generate）
- 校验 Evidence Pack / 轻量记忆快照是否可用
- 输出 jsonl 结果，便于比赛前稳定性复核
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
    # 兼容带 BOM 的 UTF-8 样本
    data = json.loads(path.read_text(encoding="utf-8-sig"))
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


def _extract_event_snapshot(orchestrator_end_event: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(orchestrator_end_event, dict):
        return {
            "event_has_evidence_pack": False,
            "event_has_memory_snapshot": False,
            "event_claims_count": 0,
            "event_traceability_count": 0,
        }
    evidence_pack = orchestrator_end_event.get("evidence_pack")
    memory_snapshot = orchestrator_end_event.get("memory_snapshot")
    claims = evidence_pack.get("claims") if isinstance(evidence_pack, dict) else None
    traceability = (
        evidence_pack.get("traceability") if isinstance(evidence_pack, dict) else None
    )
    return {
        "event_has_evidence_pack": isinstance(evidence_pack, dict),
        "event_has_memory_snapshot": isinstance(memory_snapshot, dict),
        "event_claims_count": len(claims) if isinstance(claims, list) else 0,
        "event_traceability_count": len(traceability)
        if isinstance(traceability, list)
        else 0,
    }


def _run_stream_once(
    *,
    client: httpx.Client,
    stream_url: str,
    payload: dict[str, Any],
) -> tuple[int | None, int, dict[str, Any] | None, str | None]:
    event_count = 0
    orchestrator_end_event: dict[str, Any] | None = None
    err: str | None = None
    http_code: int | None = None
    try:
        with client.stream("POST", stream_url, json=payload, timeout=None) as resp:
            http_code = resp.status_code
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                s = line.decode("utf-8") if isinstance(line, bytes) else line
                if not s.startswith("data: "):
                    continue
                body = s[6:]
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
                    orchestrator_end_event = event
                    break
                if event.get("event") == "error":
                    err = str(event.get("error") or "stream error")
                    break
    except Exception as e:
        err = str(e)
    return http_code, event_count, orchestrator_end_event, err


def run_one_sample(
    *,
    client: httpx.Client,
    api_base: str,
    sample_path: Path,
    timeout_sec: float,
    status_poll_sec: float,
    force_debate_rounds: int | None,
    use_stream: bool,
) -> dict[str, Any]:
    payload = _load_payload(sample_path)
    session_id = str(payload.get("session_id") or uuid.uuid4())
    payload["session_id"] = session_id
    if force_debate_rounds is not None:
        payload["debate_rounds"] = force_debate_rounds

    started = time.time()
    generate_url = f"{api_base}/api/v2/market-insight/generate"
    stream_url = f"{api_base}/api/v2/market-insight/stream"
    status_url = f"{api_base}/api/v2/market-insight/status/{session_id}"

    record: dict[str, Any] = {
        "sample": sample_path.name,
        "session_id": session_id,
        "started_at": _now_iso(),
        "ok": False,
        "entrypoint": "stream" if use_stream else "generate",
        "generate_http": None,
        "status_http": None,
        "stream_event_count": 0,
        "error": None,
    }

    # 1) 触发执行
    orchestrator_end_event: dict[str, Any] | None = None
    if use_stream:
        http_code, event_count, end_event, stream_err = _run_stream_once(
            client=client, stream_url=stream_url, payload=payload
        )
        record["generate_http"] = http_code
        record["stream_event_count"] = event_count
        if isinstance(end_event, dict):
            orchestrator_end_event = end_event
        if stream_err:
            record["error"] = stream_err
    else:
        try:
            gen_resp = client.post(generate_url, json=payload, timeout=timeout_sec)
            record["generate_http"] = gen_resp.status_code
            gen_resp.raise_for_status()
        except Exception as e:
            record["error"] = str(e)

    # 2) 查询状态（允许异步落库延迟）
    final_status_payload: dict[str, Any] | None = None
    poll_deadline = time.time() + max(15.0, status_poll_sec)
    while time.time() < poll_deadline:
        try:
            status_resp = client.get(status_url, timeout=20.0)
            record["status_http"] = status_resp.status_code
            if status_resp.status_code == 200:
                payload_obj = status_resp.json()
                if isinstance(payload_obj, dict):
                    final_status_payload = payload_obj
                    session = payload_obj.get("session")
                    if isinstance(session, dict):
                        if isinstance(session.get("evidence_pack"), dict) and isinstance(
                            session.get("memory_snapshot"), dict
                        ):
                            break
            time.sleep(3.0)
        except Exception:
            time.sleep(3.0)

    if isinstance(final_status_payload, dict):
        record.update(_extract_status_snapshot(final_status_payload))
    else:
        record.update(
            {
                "session_status": None,
                "phase": None,
                "has_evidence_pack": False,
                "has_memory_snapshot": False,
                "claims_count": 0,
                "traceability_count": 0,
            }
        )

    record.update(_extract_event_snapshot(orchestrator_end_event))

    # 3) 判定：优先 status；若 status 仍未回写，允许使用 orchestrator_end 兜底
    status_ok = bool(
        record["has_evidence_pack"]
        and record["has_memory_snapshot"]
        and record["claims_count"] >= 1
        and record["traceability_count"] >= 1
    )
    event_ok = bool(
        record["event_has_evidence_pack"]
        and record["event_has_memory_snapshot"]
        and record["event_claims_count"] >= 1
        and record["event_traceability_count"] >= 1
    )
    record["ok"] = status_ok or event_ok

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
        default=600.0,
        help="触发执行的超时秒数（仅 generate 模式使用）",
    )
    parser.add_argument(
        "--status-poll-sec",
        type=float,
        default=120.0,
        help="状态轮询总时长（秒）",
    )
    parser.add_argument(
        "--force-debate-rounds",
        type=int,
        default=0,
        help="强制覆盖样本 debate_rounds（默认 0，加速验收）",
    )
    parser.add_argument(
        "--mode",
        choices=["stream", "generate"],
        default="stream",
        help="回放入口，默认 stream（推荐）",
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

    # trust_env=False：避免读取系统代理导致本地回环请求被代理劫持
    with httpx.Client(trust_env=False) as client:
        for sample_path in sample_files:
            record = run_one_sample(
                client=client,
                api_base=args.api_base.rstrip("/"),
                sample_path=sample_path,
                timeout_sec=max(10.0, args.timeout_sec),
                status_poll_sec=max(15.0, args.status_poll_sec),
                force_debate_rounds=args.force_debate_rounds,
                use_stream=args.mode == "stream",
            )
            records.append(record)
            print(
                f"[{record['sample']}] ok={record['ok']} "
                f"entry={record.get('entrypoint')} "
                f"generate={record.get('generate_http')} "
                f"status={record.get('status_http')} "
                f"phase={record.get('phase')} "
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
