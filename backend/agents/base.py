# backend/agents/base.py
"""
BaseAgent 抽象类
定义所有 Agent 的统一接口，支持 LangGraph 集成
"""

from abc import ABC, abstractmethod
from typing import Generator, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging
import time
import uuid

from core.ark_client import ArkClientWrapper, get_ark_client
from core.config import settings

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent 执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentOutput:
    """Agent 输出结构"""
    agent_name: str
    content: str
    sources: list[str] = field(default_factory=list)
    confidence: float = 1.0
    thinking: Optional[str] = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    status: AgentStatus = AgentStatus.COMPLETED
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "content": self.content,
            "sources": self.sources,
            "confidence": self.confidence,
            "thinking": self.thinking,
            "artifacts": self.artifacts,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "error_message": self.error_message,
        }


@dataclass
class AgentContext:
    """Agent 执行上下文"""
    session_id: str
    profile: dict[str, Any]
    shared_memory: dict[str, Any] = field(default_factory=dict)
    other_agent_outputs: list[AgentOutput] = field(default_factory=list)
    debate_round: int = 0
    
    def get_agent_output(self, agent_name: str) -> Optional[AgentOutput]:
        """获取指定 Agent 的输出"""
        for output in self.other_agent_outputs:
            if output.agent_name == agent_name:
                return output
        return None


class BaseAgent(ABC):
    """
    Agent 抽象基类
    
    所有专业 Agent 必须继承此类并实现以下方法：
    - get_system_prompt(): 返回系统提示词
    - get_user_prompt(): 返回用户提示词
    
    可选重写：
    - execute(): 自定义执行逻辑
    - post_process(): 后处理输出
    """
    
    # Agent 名称，子类必须定义
    name: str = "base_agent"
    
    # Agent 描述
    description: str = "基础 Agent"
    
    # 是否使用 web_search
    use_websearch: bool = True
    
    # web_search 结果数量限制
    websearch_limit: int = 15
    
    # 使用的模型
    model: str = settings.default_model
    
    def __init__(
        self,
        ark_client: Optional[ArkClientWrapper] = None,
        stream_writer: Optional[Callable[[dict], None]] = None
    ):
        """
        初始化 Agent
        
        Args:
            ark_client: Ark 客户端，不传则使用默认单例
            stream_writer: LangGraph 流式写入器 (get_stream_writer())
        """
        self.ark_client = ark_client or get_ark_client()
        self.stream_writer = stream_writer
        self._execution_id = None
    
    def _emit_event(self, event_type: str, **data):
        """发送流式事件"""
        if self.stream_writer:
            self.stream_writer({
                "event": event_type,
                "agent": self.name,
                **data
            })
    
    @abstractmethod
    def get_system_prompt(self, context: AgentContext) -> str:
        """
        获取系统提示词
        
        Args:
            context: Agent 执行上下文
        
        Returns:
            str: 系统提示词
        """
        pass
    
    @abstractmethod
    def get_user_prompt(self, context: AgentContext) -> str:
        """
        获取用户提示词
        
        Args:
            context: Agent 执行上下文
        
        Returns:
            str: 用户提示词
        """
        pass
    
    def post_process(self, content: str, context: AgentContext) -> str:
        """
        后处理输出内容
        
        Args:
            content: 原始输出内容
            context: Agent 执行上下文
        
        Returns:
            str: 处理后的内容
        """
        return content
    
    def execute_stream(self, context: AgentContext) -> Generator[str, None, AgentOutput]:
        """
        流式执行 Agent
        
        Args:
            context: Agent 执行上下文
        
        Yields:
            str: 流式输出的内容片段
        
        Returns:
            AgentOutput: 最终输出结果
        """
        self._execution_id = str(uuid.uuid4())
        start_time = time.time()
        
        # 发送开始事件
        self._emit_event("agent_start", execution_id=self._execution_id)
        
        try:
            system_prompt = self.get_system_prompt(context)
            user_prompt = self.get_user_prompt(context)
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            content_parts = []
            thinking_parts = []
            is_thinking = True
            
            # 发送 thinking 开始
            self._emit_event("agent_thinking")
            
            for chunk in self.ark_client.create_response_stream(
                messages=messages,
                model=self.model,
                use_websearch=self.use_websearch,
                websearch_limit=self.websearch_limit
            ):
                # 检测思考结束标记
                if "<<<THINKING_ENDS>>>" in chunk or "<<<<THINKING_ENDS>>>>" in chunk:
                    is_thinking = False
                    self._emit_event("agent_output")
                    continue
                
                # 跳过报告开始标记
                if "<<<REPORT_STARTS>>>" in chunk or "<<<<REPORT_STARTS>>>>" in chunk:
                    continue
                
                if is_thinking:
                    thinking_parts.append(chunk)
                else:
                    content_parts.append(chunk)
                
                # 发送流式内容
                self._emit_event(
                    "agent_chunk" if not is_thinking else "agent_thinking_chunk",
                    content=chunk
                )
                yield chunk
            
            # 后处理
            full_content = "".join(content_parts)
            full_content = self.post_process(full_content, context)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            output = AgentOutput(
                agent_name=self.name,
                content=full_content,
                thinking="".join(thinking_parts) if thinking_parts else None,
                duration_ms=duration_ms,
                status=AgentStatus.COMPLETED
            )
            
            # 发送结束事件
            self._emit_event(
                "agent_end",
                status="completed",
                duration_ms=duration_ms
            )
            
            logger.info(f"Agent {self.name} 执行完成，耗时 {duration_ms}ms")
            return output
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            self._emit_event(
                "agent_error",
                error=str(e),
                duration_ms=duration_ms
            )
            
            logger.error(f"Agent {self.name} 执行失败: {e}")
            
            return AgentOutput(
                agent_name=self.name,
                content="",
                duration_ms=duration_ms,
                status=AgentStatus.FAILED,
                error_message=str(e)
            )
    
    def execute(self, context: AgentContext) -> AgentOutput:
        """
        非流式执行 Agent
        
        Args:
            context: Agent 执行上下文
        
        Returns:
            AgentOutput: 输出结果
        """
        output = None
        for _ in self.execute_stream(context):
            pass  # 消费所有流式输出
        # execute_stream 是生成器，需要处理返回值
        # 由于 Python 生成器的特性，需要通过 StopIteration 获取返回值
        gen = self.execute_stream(context)
        try:
            while True:
                next(gen)
        except StopIteration as e:
            output = e.value
        return output
