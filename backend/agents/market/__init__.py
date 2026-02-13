# backend/agents/market/__init__.py
"""
市场分析 Agent 模块

包含 5 个专业分析 Agent：
- TrendScoutAgent: 趋势侦察员
- CompetitorAnalystAgent: 竞争分析师
- RegulationCheckerAgent: 法规检查员
- SocialSentinelAgent: 社媒哨兵
- SynthesizerAgent: 综合分析师
"""

from .trend_scout import TrendScoutAgent
from .competitor_analyst import CompetitorAnalystAgent
from .regulation_checker import RegulationCheckerAgent
from .social_sentinel import SocialSentinelAgent
from .synthesizer import SynthesizerAgent

__all__ = [
    "TrendScoutAgent",
    "CompetitorAnalystAgent",
    "RegulationCheckerAgent",
    "SocialSentinelAgent",
    "SynthesizerAgent",
]
