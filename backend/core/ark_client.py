# backend/core/ark_client.py
"""
火山引擎 Ark 客户端封装
统一管理 API 调用，支持 Responses API + web_search + Thinking 模式
"""

from typing import Generator, Optional, Any, Literal
from functools import lru_cache
from dataclasses import dataclass
from enum import Enum
import logging

from volcenginesdkarkruntime import Ark

from .config import settings, ThinkingMode
from .exceptions import ConfigurationError, ToolExecutionError

logger = logging.getLogger(__name__)


# ============================================
# 流式事件类型定义
# ============================================


class StreamEventType(str, Enum):
    """流式事件类型"""

    # 内容事件
    THINKING_DELTA = "thinking_delta"  # 思考过程增量
    OUTPUT_DELTA = "output_delta"  # 最终输出增量

    # 搜索事件
    SEARCH_START = "search_start"  # 搜索开始
    SEARCH_PROGRESS = "search_progress"  # 搜索进行中
    SEARCH_COMPLETE = "search_complete"  # 搜索完成

    # 生命周期事件
    RESPONSE_START = "response_start"  # 响应开始
    RESPONSE_COMPLETE = "response_complete"  # 响应完成
    ERROR = "error"  # 错误


@dataclass
class StreamEvent:
    """流式事件结构"""

    type: StreamEventType
    content: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "content": self.content,
            "metadata": self.metadata or {},
        }


class ArkClientWrapper:
    """
    火山引擎 Ark 客户端包装类

    主要功能：
    1. 统一管理 API 密钥和配置
    2. 封装 Responses API 调用 (支持 web_search)
    3. 支持 Thinking 模式 (Kimi K2 Thinking)
    4. 解析原生 chunk.type 区分思考/输出
    5. 提供流式和非流式调用接口
    6. 返回结构化流式事件
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.ark_api_key
        self.base_url = base_url or settings.ark_base_url

        if not self.api_key:
            raise ConfigurationError("ARK_API_KEY 未配置")

        self._client = Ark(api_key=self.api_key)

    @property
    def client(self) -> Ark:
        """获取原始 Ark 客户端"""
        return self._client

    def create_response_stream_v2(
        self,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
        use_websearch: bool = False,
        websearch_limit: int = 15,
        thinking_mode: ThinkingMode = ThinkingMode.DISABLED,
        **kwargs,
    ) -> Generator[StreamEvent, None, dict[str, Any]]:
        """
        创建流式响应 v2 (返回结构化事件)

        Args:
            messages: 消息列表，格式为 [{"role": "system/user", "content": "..."}]
            model: 模型名称，默认使用配置中的 default_model
            use_websearch: 是否启用联网搜索
            websearch_limit: 联网搜索结果数量限制
            thinking_mode: Thinking 模式 (auto/enabled/disabled)
            **kwargs: 其他参数传递给 API

        Yields:
            StreamEvent: 结构化流式事件

        Returns:
            dict: 完整结果 {"output": str, "thinking": str|None, "sources": list}
        """
        model = model or settings.default_model

        # 兼容调用方可能传入 None 的情况
        if thinking_mode is None:
            thinking_mode = ThinkingMode.DISABLED

        # 转换消息格式为 Responses API 格式
        input_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Responses API 需要 content 为数组格式
            if isinstance(content, str):
                content = [{"type": "input_text", "text": content}]

            input_messages.append({"role": role, "content": content})

        # 构建请求参数
        request_params = {
            "model": model,
            "input": input_messages,
            "stream": True,
            **kwargs,
        }

        # 添加 web_search 工具
        if use_websearch:
            request_params["tools"] = [{"type": "web_search", "limit": websearch_limit}]

        # 添加 Thinking 模式 (仅对支持的模型生效)
        if thinking_mode != ThinkingMode.DISABLED:
            request_params["extra_body"] = {"thinking": {"type": thinking_mode.value}}

        logger.debug(
            f"调用 Ark Responses API: model={model}, "
            f"use_websearch={use_websearch}, thinking_mode={thinking_mode.value}"
        )

        # 累积结果
        thinking_parts: list[str] = []
        output_parts: list[str] = []
        sources: list[str] = []

        try:
            # 发送开始事件
            yield StreamEvent(type=StreamEventType.RESPONSE_START)

            response = self._client.responses.create(**request_params)

            for chunk in response:
                # 获取 chunk.type 用于区分事件类型
                chunk_type = getattr(chunk, "type", None)

                # 处理不同类型的 chunk
                if chunk_type == "response.reasoning_summary_text.delta":
                    # 思考过程增量
                    delta = getattr(chunk, "delta", "")
                    if delta:
                        thinking_parts.append(delta)
                        yield StreamEvent(
                            type=StreamEventType.THINKING_DELTA, content=delta
                        )

                elif chunk_type == "response.output_text.delta":
                    # 最终输出增量
                    delta = getattr(chunk, "delta", "")
                    if delta:
                        output_parts.append(delta)
                        yield StreamEvent(
                            type=StreamEventType.OUTPUT_DELTA, content=delta
                        )

                elif chunk_type == "response.web_search_call.in_progress":
                    # 搜索进行中
                    yield StreamEvent(
                        type=StreamEventType.SEARCH_PROGRESS,
                        metadata={"status": "in_progress"},
                    )

                elif chunk_type == "response.web_search_call.completed":
                    # 搜索完成，提取来源
                    search_results = getattr(chunk, "results", [])
                    for result in search_results:
                        url = getattr(result, "url", None)
                        if url:
                            sources.append(url)
                    yield StreamEvent(
                        type=StreamEventType.SEARCH_COMPLETE,
                        metadata={"sources_count": len(sources)},
                    )

                elif chunk_type == "response.web_search_call.searching":
                    # 搜索开始
                    yield StreamEvent(type=StreamEventType.SEARCH_START)

                else:
                    # 兼容旧格式：直接从 delta 属性获取
                    delta_content = getattr(chunk, "delta", None)
                    if isinstance(delta_content, str) and delta_content:
                        output_parts.append(delta_content)
                        yield StreamEvent(
                            type=StreamEventType.OUTPUT_DELTA, content=delta_content
                        )

            # 发送完成事件
            yield StreamEvent(
                type=StreamEventType.RESPONSE_COMPLETE,
                metadata={
                    "has_thinking": bool(thinking_parts),
                    "sources_count": len(sources),
                },
            )

            # 返回完整结果
            return {
                "output": "".join(output_parts),
                "thinking": "".join(thinking_parts) if thinking_parts else None,
                "sources": sources,
            }

        except Exception as e:
            logger.error(f"Ark API 调用失败: {e}")
            yield StreamEvent(type=StreamEventType.ERROR, content=str(e))
            raise ToolExecutionError(
                message=f"Ark API 调用失败: {e}",
                tool_name="ark_responses",
                details={"model": model, "use_websearch": use_websearch},
            )

    def create_response_stream(
        self,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
        use_websearch: bool = False,
        websearch_limit: int = 15,
        thinking_mode: ThinkingMode = ThinkingMode.DISABLED,
        **kwargs,
    ) -> Generator[str, None, None]:
        """
        创建流式响应 (兼容旧接口，仅返回输出内容)

        Args:
            messages: 消息列表，格式为 [{"role": "system/user", "content": "..."}]
            model: 模型名称，默认使用配置中的 default_model
            use_websearch: 是否启用联网搜索
            websearch_limit: 联网搜索结果数量限制
            thinking_mode: Thinking 模式
            **kwargs: 其他参数传递给 API

        Yields:
            str: 流式返回的内容片段 (仅输出，不含思考)
        """
        gen = self.create_response_stream_v2(
            messages=messages,
            model=model,
            use_websearch=use_websearch,
            websearch_limit=websearch_limit,
            thinking_mode=thinking_mode,
            **kwargs,
        )

        try:
            for event in gen:
                if event.type == StreamEventType.OUTPUT_DELTA and event.content:
                    yield event.content
        except StopIteration:
            pass

    def create_response(
        self,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
        use_websearch: bool = False,
        websearch_limit: int = 15,
        thinking_mode: ThinkingMode = ThinkingMode.DISABLED,
        **kwargs,
    ) -> str:
        """
        创建非流式响应 (使用 Responses API)

        Args:
            messages: 消息列表
            model: 模型名称
            use_websearch: 是否启用联网搜索
            websearch_limit: 联网搜索结果数量限制
            thinking_mode: Thinking 模式
            **kwargs: 其他参数

        Returns:
            str: 完整响应内容
        """
        content_parts = []
        for chunk in self.create_response_stream(
            messages=messages,
            model=model,
            use_websearch=use_websearch,
            websearch_limit=websearch_limit,
            thinking_mode=thinking_mode,
            **kwargs,
        ):
            content_parts.append(chunk)
        return "".join(content_parts)

    def create_response_full(
        self,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
        use_websearch: bool = False,
        websearch_limit: int = 15,
        thinking_mode: ThinkingMode = ThinkingMode.DISABLED,
        **kwargs,
    ) -> dict[str, Any]:
        """
        创建完整响应 (包含思考过程和来源)

        Args:
            messages: 消息列表
            model: 模型名称
            use_websearch: 是否启用联网搜索
            websearch_limit: 联网搜索结果数量限制
            thinking_mode: Thinking 模式
            **kwargs: 其他参数

        Returns:
            dict: {"output": str, "thinking": str|None, "sources": list}
        """
        gen = self.create_response_stream_v2(
            messages=messages,
            model=model,
            use_websearch=use_websearch,
            websearch_limit=websearch_limit,
            thinking_mode=thinking_mode,
            **kwargs,
        )

        result = None
        try:
            while True:
                next(gen)
        except StopIteration as e:
            result = e.value

        return result or {"output": "", "thinking": None, "sources": []}


@lru_cache()
def get_ark_client() -> ArkClientWrapper:
    """获取 Ark 客户端单例"""
    return ArkClientWrapper()
