# backend/memory/__init__.py
"""
共享记忆模块：提供 Phase 3 轻量记忆快照能力。
"""

from .session_snapshot import build_memory_snapshot

__all__ = ["build_memory_snapshot"]
