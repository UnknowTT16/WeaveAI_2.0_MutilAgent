# backend/agents/debate/__init__.py
"""
辩论 Agent 模块

包含辩论相关的 Agent：
- ChallengerAgent: 红队审查官 (质疑方)
"""

from .challenger import ChallengerAgent

__all__ = [
    "ChallengerAgent",
]
