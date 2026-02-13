# backend/schemas/v2/__init__.py
"""
v2 API Schema 定义
"""

from .requests import (
    UserProfile,
    CreateSessionRequest,
    MarketInsightRequest,
)
from .responses import (
    SessionResponse,
    AgentExecutionResponse,
    DebateRoundResponse,
    MarketInsightResponse,
    WorkflowStatus,
)
from .events import SSEEvent, SSEEventType

__all__ = [
    # Requests
    "UserProfile",
    "CreateSessionRequest",
    "MarketInsightRequest",
    # Responses
    "SessionResponse",
    "AgentExecutionResponse",
    "DebateRoundResponse",
    "MarketInsightResponse",
    "WorkflowStatus",
    # Events
    "SSEEvent",
    "SSEEventType",
]
