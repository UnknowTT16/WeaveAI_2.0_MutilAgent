# backend/schemas/v2/responses.py
"""
v2 API 响应模型
"""

from typing import Optional, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    """工作流状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MarketInsightResponse(BaseModel):
    """市场洞察报告响应"""

    session_id: str
    status: WorkflowStatus = WorkflowStatus.COMPLETED
    report: str = Field(default="", description="综合报告内容")
    report_html_url: Optional[str] = Field(default=None, description="HTML 报告地址")
    evidence_pack: Optional[dict[str, Any]] = Field(
        default=None, description="Phase 3 证据包"
    )
    memory_snapshot: Optional[dict[str, Any]] = Field(
        default=None, description="Phase 3 轻量记忆快照"
    )
    agent_results: list[dict[str, Any]] = Field(
        default_factory=list, description="各 Agent 执行结果"
    )
    debate_summary: Optional[dict[str, Any]] = Field(
        default=None, description="辩论摘要"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    error_message: Optional[str] = None


class SessionResponse(BaseModel):
    """会话响应"""

    session_id: str
    status: str = Field(default="active", description="会话状态")
    created_at: datetime = Field(default_factory=datetime.now)
    profile: Optional[dict] = None


class AgentExecutionResponse(BaseModel):
    """Agent 执行响应"""

    execution_id: str
    agent_name: str
    status: str = Field(default="pending", description="执行状态")
    thinking: Optional[str] = None
    output: Optional[str] = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class DebateRoundResponse(BaseModel):
    """辩论轮次响应"""

    round_number: int
    round_type: str = Field(
        description="辩论轮次类型",
        examples=["independent", "challenge", "respond", "consensus"],
    )
    participants: list[str] = Field(default_factory=list)
    challenges: list[dict] = Field(default_factory=list)
    responses: list[dict] = Field(default_factory=list)
    consensus: Optional[dict] = None
    created_at: datetime = Field(default_factory=datetime.now)


class EntityResponse(BaseModel):
    """实体响应"""

    entity_id: str
    entity_type: str
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)
    source_agent: Optional[str] = None
    confidence: float = 1.0


class ReportResponse(BaseModel):
    """报告响应"""

    report_id: str
    report_url: str
    pdf_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
