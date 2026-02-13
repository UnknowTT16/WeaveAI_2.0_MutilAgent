# backend/core/__init__.py
"""
核心模块：配置、客户端、异常、图引擎、依赖注入
"""

from .config import settings
from .ark_client import get_ark_client, ArkClientWrapper
from .exceptions import (
    WeaveAIException, 
    AgentExecutionError, 
    ToolExecutionError,
    GraphExecutionError,
    DebateError,
)
from .graph_engine import (
    IGraphEngine,
    MarketInsightGraphEngine,
    MarketInsightState,
    WorkflowPhase,
    AgentResult,
    DebateExchange,
    create_market_insight_engine,
)

__all__ = [
    # 配置
    "settings",
    # 客户端
    "get_ark_client",
    "ArkClientWrapper",
    # 异常
    "WeaveAIException",
    "AgentExecutionError",
    "ToolExecutionError",
    "GraphExecutionError",
    "DebateError",
    # 图引擎
    "IGraphEngine",
    "MarketInsightGraphEngine",
    "MarketInsightState",
    "WorkflowPhase",
    "AgentResult",
    "DebateExchange",
    "create_market_insight_engine",
]
