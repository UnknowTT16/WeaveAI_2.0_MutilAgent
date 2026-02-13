# backend/schemas/v2/events.py
"""
SSE 事件协议定义
v2 API 流式事件类型（含重试/辩论扩展）
"""

from enum import Enum
from typing import Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field


class SSEEventType(str, Enum):
    """
    SSE 事件类型枚举

    编排器事件：
    - orchestrator_start: 编排器开始
    - orchestrator_end: 编排器结束

    Agent 生命周期事件：
    - agent_start: Agent 开始执行
    - agent_thinking: Agent 思考过程
    - agent_output: Agent 输出内容
    - agent_end: Agent 执行结束
    - agent_error: Agent 执行错误

    工具调用事件：
    - tool_start: 工具开始执行
    - tool_end: 工具执行结束
    - tool_error: 工具执行错误

    工作流事件：
    - checkpoint: 工作流保存断点
    - retry: 节点/工具重试
    - handoff: Agent 交接
    - memory_update: 记忆更新

    辩论事件：
    - debate_round_start: 辩论轮次开始
    - agent_challenge: Agent 提出质疑
    - agent_respond: Agent 回应质疑
    - consensus_reached: 达成共识
    """

    # 编排器事件
    ORCHESTRATOR_START = "orchestrator_start"
    ORCHESTRATOR_END = "orchestrator_end"

    # Agent 生命周期事件
    AGENT_START = "agent_start"
    AGENT_THINKING = "agent_thinking"
    AGENT_THINKING_CHUNK = "agent_thinking_chunk"
    AGENT_OUTPUT = "agent_output"
    AGENT_CHUNK = "agent_chunk"
    AGENT_END = "agent_end"
    AGENT_ERROR = "agent_error"
    GATHER_COMPLETE = "gather_complete"

    # 工具调用事件
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    TOOL_ERROR = "tool_error"

    # 工作流事件
    CHECKPOINT = "checkpoint"
    RETRY = "retry"
    HANDOFF = "handoff"
    MEMORY_UPDATE = "memory_update"

    # 辩论事件
    DEBATE_ROUND_START = "debate_round_start"
    DEBATE_ROUND_END = "debate_round_end"
    AGENT_CHALLENGE = "agent_challenge"
    AGENT_CHALLENGE_END = "agent_challenge_end"
    AGENT_RESPOND = "agent_respond"
    AGENT_RESPOND_END = "agent_respond_end"
    AGENT_FOLLOWUP = "agent_followup"
    AGENT_FOLLOWUP_END = "agent_followup_end"
    CONSENSUS_REACHED = "consensus_reached"

    # 通用错误
    ERROR = "error"


class SSEEvent(BaseModel):
    """
    SSE 事件基类

    所有流式事件都继承此结构
    """

    event: SSEEventType = Field(..., description="事件类型")
    timestamp: datetime = Field(default_factory=datetime.now, description="事件时间戳")

    # Agent 相关
    agent: Optional[str] = Field(default=None, description="Agent 名称")

    # 内容
    content: Optional[str] = Field(default=None, description="事件内容")

    # 工具相关
    tool: Optional[str] = Field(default=None, description="工具名称")
    input: Optional[dict] = Field(default=None, description="工具输入")
    output: Optional[dict] = Field(default=None, description="工具输出")

    # 状态相关
    status: Optional[str] = Field(default=None, description="状态")
    duration_ms: Optional[int] = Field(default=None, description="耗时(毫秒)")

    # 错误相关
    error: Optional[str] = Field(default=None, description="错误信息")
    retry: Optional[int] = Field(default=None, description="重试次数")
    attempt: Optional[int] = Field(default=None, description="当前尝试次数")
    max_attempts: Optional[int] = Field(default=None, description="最大尝试次数")
    backoff_ms: Optional[int] = Field(default=None, description="退避毫秒")
    degrade_mode: Optional[str] = Field(default=None, description="降级策略")

    # 辩论相关
    round_number: Optional[int] = Field(default=None, description="辩论轮次")
    round_type: Optional[str] = Field(default=None, description="辩论类型")
    from_agent: Optional[str] = Field(default=None, description="发起 Agent")
    to_agent: Optional[str] = Field(default=None, description="目标 Agent")
    challenge_content: Optional[str] = Field(default=None, description="质疑内容")
    response_content: Optional[str] = Field(default=None, description="回应内容")
    followup_content: Optional[str] = Field(default=None, description="追问内容")
    content_preview: Optional[str] = Field(default=None, description="内容预览")
    revised: Optional[bool] = Field(default=None, description="是否修正观点")

    # 共识相关
    consensus_summary: Optional[str] = Field(default=None, description="共识摘要")
    dissent_points: Optional[list[str]] = Field(default=None, description="分歧点")
    confidence: Optional[float] = Field(default=None, description="置信度")

    # 检查点相关
    node_id: Optional[str] = Field(default=None, description="节点 ID")
    state_ref: Optional[str] = Field(default=None, description="状态引用")

    # 重试追踪相关
    target_type: Optional[str] = Field(default=None, description="重试目标类型")
    target_id: Optional[str] = Field(default=None, description="重试目标 ID")

    # 交接相关
    from_: Optional[str] = Field(default=None, alias="from", description="来源")
    to: Optional[str] = Field(default=None, description="目标")
    context: Optional[Any] = Field(default=None, description="上下文")

    # 最终报告
    final_report: Optional[str] = Field(default=None, description="最终报告")

    # 扩展数据
    extra: Optional[dict[str, Any]] = Field(default=None, description="扩展数据")

    def to_sse_string(self) -> str:
        """转换为 SSE 格式字符串"""
        import json

        data = self.model_dump(exclude_none=True, by_alias=True)
        # 将 timestamp 转为 ISO 格式
        if "timestamp" in data:
            data["timestamp"] = data["timestamp"].isoformat()
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ============================================
# 便捷工厂函数
# ============================================


def create_orchestrator_start_event() -> SSEEvent:
    """创建编排器开始事件"""
    return SSEEvent(event=SSEEventType.ORCHESTRATOR_START)


def create_orchestrator_end_event(final_report: str) -> SSEEvent:
    """创建编排器结束事件"""
    return SSEEvent(event=SSEEventType.ORCHESTRATOR_END, final_report=final_report)


def create_agent_start_event(agent: str) -> SSEEvent:
    """创建 Agent 开始事件"""
    return SSEEvent(event=SSEEventType.AGENT_START, agent=agent)


def create_agent_end_event(
    agent: str, status: str = "completed", duration_ms: int = 0
) -> SSEEvent:
    """创建 Agent 结束事件"""
    return SSEEvent(
        event=SSEEventType.AGENT_END,
        agent=agent,
        status=status,
        duration_ms=duration_ms,
    )


def create_agent_error_event(agent: str, error: str) -> SSEEvent:
    """创建 Agent 错误事件"""
    return SSEEvent(event=SSEEventType.AGENT_ERROR, agent=agent, error=error)


def create_debate_round_start_event(
    round_number: int, round_type: str, participants: list[str]
) -> SSEEvent:
    """创建辩论轮次开始事件"""
    return SSEEvent(
        event=SSEEventType.DEBATE_ROUND_START,
        round_number=round_number,
        round_type=round_type,
        extra={"participants": participants},
    )


def create_consensus_reached_event(
    summary: str, dissent_points: list[str], confidence: float
) -> SSEEvent:
    """创建达成共识事件"""
    return SSEEvent(
        event=SSEEventType.CONSENSUS_REACHED,
        consensus_summary=summary,
        dissent_points=dissent_points,
        confidence=confidence,
    )
