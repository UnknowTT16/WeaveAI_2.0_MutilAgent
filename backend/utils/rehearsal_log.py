"""Phase 5 彩排指标日志落盘。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import threading
from typing import Any


_LOG_LOCK = threading.Lock()
_LOGGED_SESSION_KEYS: set[str] = set()


def _rehearsal_log_path() -> Path:
    backend_dir = Path(__file__).resolve().parent.parent
    return backend_dir / "artifacts" / "phase5" / "rehearsal_metrics.jsonl"


def append_rehearsal_metric(snapshot: dict[str, Any]) -> bool:
    """将终态会话指标写入 jsonl，进程内按 session+status 去重。"""
    session_id = str(snapshot.get("session_id") or "").strip()
    status = str(snapshot.get("status") or "").strip().lower()
    if not session_id:
        return False

    dedupe_key = f"{session_id}:{status}"

    with _LOG_LOCK:
        if dedupe_key in _LOGGED_SESSION_KEYS:
            return False

        path = _rehearsal_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = dict(snapshot)
        payload.setdefault("logged_at", datetime.now(timezone.utc).isoformat())

        with path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")

        _LOGGED_SESSION_KEYS.add(dedupe_key)
        return True
