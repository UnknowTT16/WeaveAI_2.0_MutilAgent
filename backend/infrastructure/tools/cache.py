"""工具调用缓存（进程内 TTL + LRU）。"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CacheEntry:
    value: dict[str, Any]
    expire_at: float


class ToolCache:
    """用于 web_search 调用路径的轻量缓存。"""

    def __init__(self, ttl_seconds: int = 300, max_size: int = 128):
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.max_size = max(1, int(max_size))
        self._data: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def build_key(
        *,
        agent_name: str,
        model: str,
        template_version: str,
        prompt_hash: str,
        debate_round: int,
        enable_websearch: bool,
    ) -> str:
        payload = {
            "agent_name": agent_name,
            "model": model,
            "template_version": template_version,
            "prompt_hash": prompt_hash,
            "debate_round": int(debate_round),
            "enable_websearch": bool(enable_websearch),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def hash_prompt(*parts: str) -> str:
        joined = "\n\n".join(parts)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[dict[str, Any]]:
        now = time.time()
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            if entry.expire_at < now:
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return copy.deepcopy(entry.value)

    def set(self, key: str, value: dict[str, Any]) -> None:
        expire_at = time.time() + self.ttl_seconds
        with self._lock:
            self._data[key] = CacheEntry(
                value=copy.deepcopy(value), expire_at=expire_at
            )
            self._data.move_to_end(key)
            while len(self._data) > self.max_size:
                self._data.popitem(last=False)
