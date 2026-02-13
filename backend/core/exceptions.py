# backend/core/exceptions.py
"""
自定义异常类
"""

from typing import Optional, Any


class WeaveAIException(Exception):
    """WeaveAI 基础异常类"""
    
    def __init__(
        self, 
        message: str, 
        code: str = "WEAVE_ERROR",
        details: Optional[dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class AgentExecutionError(WeaveAIException):
    """Agent 执行错误"""
    
    def __init__(
        self,
        message: str,
        agent_name: str,
        details: Optional[dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code="AGENT_EXECUTION_ERROR",
            details={"agent_name": agent_name, **(details or {})}
        )
        self.agent_name = agent_name


class ToolExecutionError(WeaveAIException):
    """工具执行错误"""
    
    def __init__(
        self,
        message: str,
        tool_name: str,
        agent_name: Optional[str] = None,
        details: Optional[dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code="TOOL_EXECUTION_ERROR",
            details={
                "tool_name": tool_name,
                "agent_name": agent_name,
                **(details or {})
            }
        )
        self.tool_name = tool_name
        self.agent_name = agent_name


class DebateError(WeaveAIException):
    """辩论流程错误"""
    
    def __init__(
        self,
        message: str,
        round_number: int,
        details: Optional[dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code="DEBATE_ERROR",
            details={"round_number": round_number, **(details or {})}
        )
        self.round_number = round_number


class GraphExecutionError(WeaveAIException):
    """图执行错误"""
    
    def __init__(
        self,
        message: str,
        node_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code="GRAPH_EXECUTION_ERROR",
            details={"node_id": node_id, **(details or {})}
        )
        self.node_id = node_id


class ConfigurationError(WeaveAIException):
    """配置错误"""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            details=details
        )


class ValidationError(WeaveAIException):
    """数据验证错误"""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details={"field": field, **(details or {})}
        )
        self.field = field
