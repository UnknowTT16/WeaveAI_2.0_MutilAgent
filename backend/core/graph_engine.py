# backend/core/graph_engine.py
"""
LangGraph 图引擎
实现 Supervisor-Worker + 多轮辩论 的多 Agent 协作架构
"""

from abc import ABC, abstractmethod
from typing import (
    TypedDict,
    Annotated,
    Callable,
    Any,
    Optional,
    Generator,
    Literal,
    Union,
    Sequence,
)
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
import logging
import uuid
import time
from datetime import datetime
import operator
import asyncio
import threading

# LangGraph 核心导入
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send, interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer

from core.config import (
    settings,
    ThinkingMode,
    DEBATE_PEER_PAIRS,
    DEBATE_REDTEAM_TARGETS,
    AGENT_DEBATE_CHALLENGER,
    AGENT_SYNTHESIZER,
)
from core.exceptions import GraphExecutionError
from core.evidence_pack import build_evidence_pack
from memory import build_memory_snapshot
from utils.report_export import write_html_report

logger = logging.getLogger(__name__)


# ============================================
# Ark 并发自适应状态（进程内共享）
# ============================================

_ADAPTIVE_DEFAULT_LIMIT = 4
_ADAPTIVE_REDUCED_LIMIT = 2
_ADAPTIVE_FAIL_THRESHOLD = 4
_ADAPTIVE_RECOVERY_SUCCESS_STREAK = 6
_ADAPTIVE_REDUCED_WINDOW_SEC = 120.0

_ADAPTIVE_CONCURRENCY_LIMIT = _ADAPTIVE_DEFAULT_LIMIT
_ADAPTIVE_INFLIGHT_CALLS = 0
_ADAPTIVE_CONN_FAIL_STREAK = 0
_ADAPTIVE_SUCCESS_STREAK = 0
_ADAPTIVE_RECOVER_AFTER_TS = 0.0

_ADAPTIVE_STATE_LOCK = threading.Lock()
_ADAPTIVE_STATE_COND = threading.Condition(_ADAPTIVE_STATE_LOCK)


# ============================================
# 状态定义
# ============================================


class WorkflowPhase(str, Enum):
    """工作流阶段"""

    INIT = "init"  # 初始化
    GATHER = "gather"  # 并行收集
    DEBATE_PEER = "debate_peer"  # 同行评审
    DEBATE_REDTEAM = "debate_redteam"  # 红队审查
    SYNTHESIZE = "synthesize"  # 综合
    COMPLETE = "complete"  # 完成
    ERROR = "error"  # 错误


class DebateType(str, Enum):
    """辩论类型"""

    PEER_REVIEW = "peer_review"  # 同行评审 (Worker 互相质疑)
    RED_TEAM = "red_team"  # 红队审查 (DeepSeek 审查所有)


@dataclass
class AgentResult:
    """单个 Agent 的执行结果"""

    agent_name: str
    content: str
    sources: list[str] = field(default_factory=list)
    thinking: Optional[str] = None
    confidence: float = 1.0
    duration_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "content": self.content,
            "sources": self.sources,
            "thinking": self.thinking,
            "confidence": self.confidence,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


@dataclass
class DebateExchange:
    """辩论交换记录"""

    round_number: int
    debate_type: DebateType
    challenger: str
    responder: str
    challenge_content: str
    response_content: str
    followup_content: Optional[str] = None  # 二次追问/确认
    revised: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_number": self.round_number,
            "debate_type": self.debate_type.value,
            "challenger": self.challenger,
            "responder": self.responder,
            "challenge_content": self.challenge_content,
            "response_content": self.response_content,
            "followup_content": self.followup_content,
            "revised": self.revised,
        }


class MarketInsightState(TypedDict, total=False):
    """
    市场洞察工作流状态

    使用 Annotated + operator.add 实现列表累积
    """

    # 会话 ID
    session_id: str

    # 用户输入
    user_profile: dict[str, Any]

    # 工作流阶段
    phase: WorkflowPhase

    # Agent 执行结果 (累积)
    agent_results: Annotated[list[AgentResult], operator.add]

    # 辩论记录 (累积)
    debate_exchanges: Annotated[list[DebateExchange], operator.add]

    # 辩论配置
    debate_rounds: int
    current_debate_round: int
    current_debate_type: Optional[DebateType]

    # 二次回应开关
    enable_followup: bool

    # 是否启用联网搜索（覆盖各 Agent 默认配置）
    enable_websearch: bool

    # 重试与降级配置
    retry_max_attempts: int
    retry_backoff_ms: int
    degrade_mode: Literal["skip", "partial", "fail"]

    # 最终输出
    synthesized_report: Optional[str]
    report_html_url: Optional[str]
    evidence_pack: Optional[dict[str, Any]]
    memory_snapshot: Optional[dict[str, Any]]

    # 错误信息
    error: Optional[str]

    # 时间戳
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


# ============================================
# 图引擎抽象接口
# ============================================


class IGraphEngine(ABC):
    """
    图引擎抽象接口

    定义所有图引擎必须实现的方法
    """

    @abstractmethod
    def build(self) -> StateGraph:
        """构建状态图"""
        pass

    @abstractmethod
    def compile(self, checkpointer: Optional[MemorySaver] = None):
        """编译状态图"""
        pass

    @abstractmethod
    def invoke(self, initial_state: dict[str, Any]) -> dict[str, Any]:
        """同步执行工作流"""
        pass

    @abstractmethod
    def stream(
        self, initial_state: dict[str, Any]
    ) -> Generator[dict[str, Any], None, None]:
        """流式执行工作流"""
        pass


# ============================================
# LangGraph 引擎实现
# ============================================


class MarketInsightGraphEngine(IGraphEngine):
    """
    市场洞察图引擎

    实现 Supervisor-Worker + 多轮辩论 架构：

    Phase 1: 并行收集 (4 次 API 调用)
        → 4 个 Worker Agent 同时执行

    Round 1: 同行评审 (含二次回应)
        配对 A: Trend Scout ↔ Competitor Analyst
        配对 B: Regulation Checker ↔ Social Sentinel
        每个配对：质疑 → 回应 → 确认/追问 (双向)

    Round 2: 红队审查 (含二次回应)
        DeepSeek 红队逐一审查 4 个 Agent
        每个 Agent：质疑 → 回应 → 确认/追问

    Phase 3: 综合报告 (1 次 API 调用)
        Synthesizer 整合所有内容
    """

    # Agent 名称常量
    TREND_SCOUT = "trend_scout"
    COMPETITOR_ANALYST = "competitor_analyst"
    REGULATION_CHECKER = "regulation_checker"
    SOCIAL_SENTINEL = "social_sentinel"
    SYNTHESIZER = "synthesizer"

    WORKER_AGENTS = [
        TREND_SCOUT,
        COMPETITOR_ANALYST,
        REGULATION_CHECKER,
        SOCIAL_SENTINEL,
    ]

    def __init__(
        self,
        agent_factory: Optional[Callable[[str], Any]] = None,
        debate_rounds: int = settings.default_debate_rounds,
        enable_followup: bool = True,
        retry_max_attempts: int = 2,
        retry_backoff_ms: int = 300,
        degrade_mode: Literal["skip", "partial", "fail"] = "partial",
    ):
        """
        初始化图引擎

        Args:
            agent_factory: Agent 工厂函数，接收 agent_name 返回 Agent 实例
            debate_rounds: 辩论轮数 (默认 2 轮: 同行评审 + 红队审查)
            enable_followup: 是否启用二次回应
            retry_max_attempts: 节点最大重试次数
            retry_backoff_ms: 重试退避起始毫秒（指数退避）
            degrade_mode: 重试耗尽后的降级策略（skip/partial/fail）
        """
        self.agent_factory = agent_factory
        self.debate_rounds = debate_rounds
        self.enable_followup = enable_followup
        self.retry_max_attempts = max(1, int(retry_max_attempts))
        self.retry_backoff_ms = max(0, int(retry_backoff_ms))
        self.degrade_mode = (
            degrade_mode if degrade_mode in ("skip", "partial", "fail") else "partial"
        )
        self._graph: Optional[StateGraph] = None
        self._compiled_graph = None
        self._checkpointer: Optional[MemorySaver] = None

    def build(self) -> StateGraph:
        """
        构建市场洞察状态图

        架构：
            START
              ↓
            orchestrator (分发任务)
              ↓
            [4 Workers 并行]
              ↓
            gather (收集结果)
              ↓
            debate_peer (Round 1: 同行评审)
              ↓
            debate_redteam (Round 2: 红队审查)
              ↓
            synthesizer (综合报告)
              ↓
            END
        """
        builder = StateGraph(MarketInsightState)

        # 添加节点
        builder.add_node("orchestrator", self._orchestrator_node)
        builder.add_node(self.TREND_SCOUT, self._create_agent_node(self.TREND_SCOUT))
        builder.add_node(
            self.COMPETITOR_ANALYST, self._create_agent_node(self.COMPETITOR_ANALYST)
        )
        builder.add_node(
            self.REGULATION_CHECKER, self._create_agent_node(self.REGULATION_CHECKER)
        )
        builder.add_node(
            self.SOCIAL_SENTINEL, self._create_agent_node(self.SOCIAL_SENTINEL)
        )
        builder.add_node("gather", self._gather_node)
        builder.add_node("debate_peer", self._debate_peer_node)
        builder.add_node("debate_redteam", self._debate_redteam_node)
        builder.add_node("synthesizer", self._synthesizer_node)

        # 定义边
        builder.add_edge(START, "orchestrator")

        # orchestrator -> 并行分发到 4 个 Agent
        builder.add_conditional_edges(
            "orchestrator", self._dispatch_to_workers, self.WORKER_AGENTS
        )

        # 4 个 Agent -> gather
        for agent_name in self.WORKER_AGENTS:
            builder.add_edge(agent_name, "gather")

        # gather -> debate_peer / synthesizer（根据 debate_rounds 动态路由）
        builder.add_conditional_edges(
            "gather",
            self._route_after_gather,
            {
                "debate_peer": "debate_peer",
                "synthesizer": "synthesizer",
            },
        )

        # debate_peer -> debate_redteam / synthesizer（根据 debate_rounds 动态路由）
        builder.add_conditional_edges(
            "debate_peer",
            self._route_after_peer_debate,
            {
                "debate_redteam": "debate_redteam",
                "synthesizer": "synthesizer",
            },
        )

        # debate_redteam -> synthesizer
        builder.add_edge("debate_redteam", "synthesizer")

        # synthesizer -> END
        builder.add_edge("synthesizer", END)

        self._graph = builder
        return builder

    def compile(self, checkpointer: Optional[MemorySaver] = None):
        """编译状态图"""
        if self._graph is None:
            self.build()

        self._checkpointer = checkpointer or MemorySaver()
        self._compiled_graph = self._graph.compile(checkpointer=self._checkpointer)

        logger.info("MarketInsightGraphEngine 编译完成")

    def invoke(self, initial_state: dict[str, Any]) -> dict[str, Any]:
        """同步执行工作流"""
        if self._compiled_graph is None:
            self.compile()

        state = self._prepare_initial_state(initial_state)
        config = {"configurable": {"thread_id": state["session_id"]}}

        try:
            result = self._compiled_graph.invoke(state, config)
            return result
        except Exception as e:
            logger.error(f"工作流执行失败: {e}")
            raise GraphExecutionError(f"工作流执行失败: {e}")

    def stream(
        self, initial_state: dict[str, Any]
    ) -> Generator[dict[str, Any], None, None]:
        """流式执行工作流"""
        if self._compiled_graph is None:
            self.compile()

        state = self._prepare_initial_state(initial_state)
        config = {"configurable": {"thread_id": state["session_id"]}}

        try:
            for event in self._compiled_graph.stream(
                state, config, stream_mode="custom"
            ):
                yield event
        except Exception as e:
            logger.error(f"流式执行失败: {e}")
            yield {
                "event": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def _prepare_initial_state(
        self, initial_state: dict[str, Any]
    ) -> MarketInsightState:
        """准备初始状态"""
        debate_rounds = self._normalize_debate_rounds(
            initial_state.get("debate_rounds", self.debate_rounds)
        )
        retry_max_attempts = max(
            1, int(initial_state.get("retry_max_attempts", self.retry_max_attempts))
        )
        retry_backoff_ms = max(
            0, int(initial_state.get("retry_backoff_ms", self.retry_backoff_ms))
        )
        degrade_mode = self._resolve_degrade_mode(
            initial_state.get("degrade_mode", self.degrade_mode)
        )

        return {
            "session_id": initial_state.get("session_id", str(uuid.uuid4())),
            "user_profile": initial_state.get("user_profile", {}),
            "phase": WorkflowPhase.INIT,
            "agent_results": [],
            "debate_exchanges": [],
            "debate_rounds": debate_rounds,
            "current_debate_round": 0,
            "current_debate_type": None,
            "enable_followup": initial_state.get(
                "enable_followup", self.enable_followup
            ),
            "enable_websearch": initial_state.get("enable_websearch", False),
            "retry_max_attempts": retry_max_attempts,
            "retry_backoff_ms": retry_backoff_ms,
            "degrade_mode": degrade_mode,
            "synthesized_report": None,
            "error": None,
            "started_at": datetime.now(),
            "completed_at": None,
        }

    def _normalize_debate_rounds(self, value: Any) -> int:
        """将辩论轮数标准化到可执行范围。"""
        try:
            rounds = int(value)
        except Exception:
            rounds = int(self.debate_rounds)
        if rounds < 0:
            rounds = 0
        # 当前图只实现到红队轮次，>=2 统一按 2 执行
        return min(rounds, 2)

    def _resolve_degrade_mode(self, value: Any) -> Literal["skip", "partial", "fail"]:
        """规范化降级策略。"""
        if value in ("skip", "partial", "fail"):
            return value
        return "partial"

    def _emit_retry_event(
        self,
        *,
        writer: Callable,
        target_type: str,
        target_id: str,
        attempt: int,
        max_attempts: int,
        error: str,
        backoff_ms: int,
    ) -> None:
        """发送统一的重试事件。"""
        writer(
            {
                "event": "retry",
                "target_type": target_type,
                "target_id": target_id,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "error": error,
                "backoff_ms": backoff_ms,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _compute_backoff_ms(
        self, base_ms: int, attempt: int, jitter_key: Optional[str] = None
    ) -> int:
        """计算指数退避时延，并按 key 注入稳定抖动避免并发同频重试。"""
        if base_ms <= 0:
            return 0

        delay_ms = base_ms * (2 ** max(0, attempt - 1))
        if jitter_key:
            token = f"{jitter_key}:{attempt}".encode("utf-8")
            jitter_bucket = sum(token) % 41  # 0~40%
            delay_ms += int(base_ms * (jitter_bucket / 100))
        return delay_ms

    def _sleep_backoff(self, delay_ms: int) -> None:
        """按计算后的时延休眠。"""
        if delay_ms <= 0:
            return
        time.sleep(delay_ms / 1000)

    def _worker_stagger_ms(self, agent_name: str) -> int:
        """Worker 启动抖动：保持 4 并发但错峰发起首包请求。"""
        try:
            idx = self.WORKER_AGENTS.index(agent_name)
        except ValueError:
            return 0
        return idx * 120

    def _is_connection_like_error(self, error: Optional[str]) -> bool:
        """判断是否属于连接波动类错误。"""
        if not error:
            return False
        text = error.lower()
        keywords = (
            "connection error",
            "request timed out",
            "timeout",
            "connect",
            "network",
            "ssl",
            "tls",
        )
        return any(k in text for k in keywords)

    def _current_adaptive_limit(self) -> int:
        """读取当前并发上限。"""
        with _ADAPTIVE_STATE_LOCK:
            return _ADAPTIVE_CONCURRENCY_LIMIT

    @contextmanager
    def _acquire_ark_slot(self) -> Generator[int, None, None]:
        """获取 Ark 调用并发槽位，支持动态从 4 降到 2。"""
        global _ADAPTIVE_INFLIGHT_CALLS

        with _ADAPTIVE_STATE_COND:
            while _ADAPTIVE_INFLIGHT_CALLS >= _ADAPTIVE_CONCURRENCY_LIMIT:
                _ADAPTIVE_STATE_COND.wait(timeout=0.2)
            _ADAPTIVE_INFLIGHT_CALLS += 1
            current_limit = _ADAPTIVE_CONCURRENCY_LIMIT

        try:
            yield current_limit
        finally:
            with _ADAPTIVE_STATE_COND:
                _ADAPTIVE_INFLIGHT_CALLS = max(0, _ADAPTIVE_INFLIGHT_CALLS - 1)
                _ADAPTIVE_STATE_COND.notify_all()

    def _record_ark_outcome(
        self,
        *,
        success: bool,
        error: Optional[str],
        writer: Optional[Callable] = None,
    ) -> None:
        """记录 Ark 调用结果，并在必要时触发并发自适应降载/恢复。"""
        global _ADAPTIVE_CONCURRENCY_LIMIT
        global _ADAPTIVE_CONN_FAIL_STREAK
        global _ADAPTIVE_SUCCESS_STREAK
        global _ADAPTIVE_RECOVER_AFTER_TS

        changed_to: Optional[int] = None
        now_ts = time.time()

        with _ADAPTIVE_STATE_COND:
            if success:
                _ADAPTIVE_CONN_FAIL_STREAK = 0
                _ADAPTIVE_SUCCESS_STREAK += 1

                should_recover = (
                    _ADAPTIVE_CONCURRENCY_LIMIT == _ADAPTIVE_REDUCED_LIMIT
                    and now_ts >= _ADAPTIVE_RECOVER_AFTER_TS
                    and _ADAPTIVE_SUCCESS_STREAK >= _ADAPTIVE_RECOVERY_SUCCESS_STREAK
                )
                if should_recover:
                    _ADAPTIVE_CONCURRENCY_LIMIT = _ADAPTIVE_DEFAULT_LIMIT
                    changed_to = _ADAPTIVE_DEFAULT_LIMIT
                    _ADAPTIVE_SUCCESS_STREAK = 0
                    _ADAPTIVE_STATE_COND.notify_all()
            else:
                _ADAPTIVE_SUCCESS_STREAK = 0
                if self._is_connection_like_error(error):
                    _ADAPTIVE_CONN_FAIL_STREAK += 1
                    should_reduce = (
                        _ADAPTIVE_CONCURRENCY_LIMIT == _ADAPTIVE_DEFAULT_LIMIT
                        and _ADAPTIVE_CONN_FAIL_STREAK >= _ADAPTIVE_FAIL_THRESHOLD
                    )
                    if should_reduce:
                        _ADAPTIVE_CONCURRENCY_LIMIT = _ADAPTIVE_REDUCED_LIMIT
                        _ADAPTIVE_RECOVER_AFTER_TS = (
                            now_ts + _ADAPTIVE_REDUCED_WINDOW_SEC
                        )
                        changed_to = _ADAPTIVE_REDUCED_LIMIT
                        _ADAPTIVE_STATE_COND.notify_all()
                else:
                    _ADAPTIVE_CONN_FAIL_STREAK = 0

        if changed_to and writer:
            mode = "degraded" if changed_to == _ADAPTIVE_REDUCED_LIMIT else "recovered"
            writer(
                {
                    "event": "adaptive_concurrency",
                    "mode": mode,
                    "concurrency_limit": changed_to,
                    "reason": error or "network_stable",
                    "timestamp": datetime.now().isoformat(),
                }
            )

    def _route_after_gather(self, state: MarketInsightState) -> str:
        """gather 后路由：0 轮直达综合，其它进入同行评审。"""
        rounds = self._normalize_debate_rounds(state.get("debate_rounds", 0))
        return "synthesizer" if rounds <= 0 else "debate_peer"

    def _route_after_peer_debate(self, state: MarketInsightState) -> str:
        """同行评审后路由：1 轮直达综合，2 轮进入红队。"""
        rounds = self._normalize_debate_rounds(state.get("debate_rounds", 0))
        return "synthesizer" if rounds <= 1 else "debate_redteam"

    # ============================================
    # 节点实现
    # ============================================

    def _orchestrator_node(self, state: MarketInsightState) -> dict[str, Any]:
        """编排器节点：分发任务"""
        writer = get_stream_writer()

        writer(
            {
                "event": "orchestrator_start",
                "session_id": state["session_id"],
                "timestamp": datetime.now().isoformat(),
                "agents": self.WORKER_AGENTS,
                "debate_rounds": state.get("debate_rounds", 2),
            }
        )

        logger.info(f"Orchestrator 开始分发任务到 {len(self.WORKER_AGENTS)} 个 Agent")

        return {"phase": WorkflowPhase.GATHER}

    def _dispatch_to_workers(self, state: MarketInsightState) -> list[Send]:
        """使用 Send API 并行分发任务"""
        return [Send(agent_name, state) for agent_name in self.WORKER_AGENTS]

    def _create_agent_node(self, agent_name: str) -> Callable:
        """创建 Agent 节点函数"""

        def agent_node(state: MarketInsightState) -> dict[str, Any]:
            writer = get_stream_writer()
            start_time = time.time()
            max_attempts = max(1, int(state.get("retry_max_attempts", 1)))
            backoff_ms = max(0, int(state.get("retry_backoff_ms", 0)))
            forced_thinking_mode = ThinkingMode.ENABLED
            degrade_mode = self._resolve_degrade_mode(
                state.get("degrade_mode", "partial")
            )

            writer(
                {
                    "event": "agent_start",
                    "agent": agent_name,
                    "thinking_mode": forced_thinking_mode.value,
                    "adaptive_concurrency_limit": self._current_adaptive_limit(),
                    "timestamp": datetime.now().isoformat(),
                }
            )

            last_error: Optional[str] = None
            stagger_ms = self._worker_stagger_ms(agent_name)
            if stagger_ms > 0:
                self._sleep_backoff(stagger_ms)

            for attempt in range(1, max_attempts + 1):
                try:
                    thinking_parts: list[str] = []
                    sources: list[str] = []

                    if self.agent_factory:
                        agent = self.agent_factory(agent_name)

                        # 统一由工作流开关控制是否允许联网搜索
                        agent.use_websearch = bool(
                            getattr(agent, "use_websearch", False)
                        ) and bool(state.get("enable_websearch", False))

                        from agents.base import AgentContext

                        context = AgentContext(
                            session_id=state["session_id"],
                            profile=state["user_profile"],
                            other_agent_outputs=[],
                            debate_round=state.get("current_debate_round", 0),
                        )

                        content_parts: list[str] = []

                        # 使用 v2 流式接口
                        from core.ark_client import StreamEventType

                        messages = [
                            {
                                "role": "system",
                                "content": agent.get_system_prompt(context),
                            },
                            {"role": "user", "content": agent.get_user_prompt(context)},
                        ]

                        with self._acquire_ark_slot() as slot_limit:
                            if slot_limit < len(self.WORKER_AGENTS):
                                writer(
                                    {
                                        "event": "adaptive_concurrency",
                                        "mode": "degraded",
                                        "concurrency_limit": slot_limit,
                                        "agent": agent_name,
                                        "timestamp": datetime.now().isoformat(),
                                    }
                                )

                            for event in agent.ark_client.create_response_stream_v2(
                                messages=messages,
                                model=agent.model,
                                use_websearch=agent.use_websearch,
                                websearch_limit=agent.websearch_limit,
                                thinking_mode=forced_thinking_mode,
                            ):
                                if (
                                    event.type == StreamEventType.OUTPUT_DELTA
                                    and event.content
                                ):
                                    writer(
                                        {
                                            "event": "agent_chunk",
                                            "agent": agent_name,
                                            "content": event.content,
                                        }
                                    )
                                    content_parts.append(event.content)
                                elif (
                                    event.type == StreamEventType.THINKING_DELTA
                                    and event.content
                                ):
                                    writer(
                                        {
                                            "event": "agent_thinking",
                                            "agent": agent_name,
                                            "content": event.content,
                                        }
                                    )
                                    thinking_parts.append(event.content)
                                elif event.type == StreamEventType.SEARCH_START:
                                    writer(
                                        {
                                            "event": "tool_start",
                                            "tool": "web_search",
                                            "agent": agent_name,
                                            "timestamp": datetime.now().isoformat(),
                                        }
                                    )
                                elif event.type == StreamEventType.SEARCH_COMPLETE:
                                    meta = event.metadata or {}
                                    meta_sources = meta.get("sources")
                                    if isinstance(meta_sources, list):
                                        for source in meta_sources:
                                            if isinstance(source, str) and source not in sources:
                                                sources.append(source)
                                    writer(
                                        {
                                            "event": "tool_end",
                                            "tool": "web_search",
                                            "agent": agent_name,
                                            "sources_count": meta.get(
                                                "sources_count", 0
                                            ),
                                            "timestamp": datetime.now().isoformat(),
                                        }
                                    )

                        content = "".join(content_parts)
                        content = agent.post_process(content, context)

                    else:
                        target_market = state.get("user_profile", {}).get(
                            "target_market", "未指定市场"
                        )
                        supply_chain = state.get("user_profile", {}).get(
                            "supply_chain", "未指定品类"
                        )
                        content = f"[{agent_name}] 模拟输出 - 市场: {target_market} / 品类: {supply_chain}"

                    duration_ms = int((time.time() - start_time) * 1000)
                    self._record_ark_outcome(success=True, error=None, writer=writer)

                    result = AgentResult(
                        agent_name=agent_name,
                        content=content,
                        thinking="".join(thinking_parts) if thinking_parts else None,
                        sources=sources,
                        duration_ms=duration_ms,
                    )

                    writer(
                        {
                            "event": "agent_end",
                            "agent": agent_name,
                            "status": "completed",
                            "duration_ms": duration_ms,
                            "attempt": attempt,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                    return {"agent_results": [result]}

                except Exception as e:
                    last_error = str(e)
                    self._record_ark_outcome(
                        success=False, error=last_error, writer=writer
                    )
                    if attempt < max_attempts:
                        delay_ms = self._compute_backoff_ms(
                            backoff_ms, attempt, jitter_key=agent_name
                        )
                        self._emit_retry_event(
                            writer=writer,
                            target_type="agent",
                            target_id=agent_name,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            error=last_error,
                            backoff_ms=delay_ms,
                        )
                        self._sleep_backoff(delay_ms)
                        continue

                    duration_ms = int((time.time() - start_time) * 1000)

                    writer(
                        {
                            "event": "agent_error",
                            "agent": agent_name,
                            "error": last_error,
                            "duration_ms": duration_ms,
                            "attempt": attempt,
                            "degrade_mode": degrade_mode,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                    logger.error(
                        f"Agent {agent_name} 执行失败，attempt={attempt}/{max_attempts}: {last_error}"
                    )

                    if degrade_mode == "fail":
                        raise

                    if degrade_mode == "skip":
                        writer(
                            {
                                "event": "agent_end",
                                "agent": agent_name,
                                "status": "skipped",
                                "duration_ms": duration_ms,
                                "attempt": attempt,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                        return {}

                    # partial：返回失败结果，允许主链路继续
                    return {
                        "agent_results": [
                            AgentResult(
                                agent_name=agent_name,
                                content="",
                                error=last_error,
                                duration_ms=duration_ms,
                            )
                        ]
                    }

            # 理论上不会走到这里，作为保险返回
            return {
                "agent_results": [
                    AgentResult(
                        agent_name=agent_name,
                        content="",
                        error=last_error or "unknown_error",
                        duration_ms=int((time.time() - start_time) * 1000),
                    )
                ]
            }

        return agent_node

    def _gather_node(self, state: MarketInsightState) -> dict[str, Any]:
        """收集节点：等待所有 Worker 完成"""
        writer = get_stream_writer()

        completed_agents = [r.agent_name for r in state.get("agent_results", [])]

        writer(
            {
                "event": "gather_complete",
                "completed_agents": completed_agents,
                "total_results": len(state.get("agent_results", [])),
                "timestamp": datetime.now().isoformat(),
            }
        )

        logger.info(f"收集完成，共 {len(state.get('agent_results', []))} 个结果")

        rounds = self._normalize_debate_rounds(state.get("debate_rounds", 0))
        next_phase = (
            WorkflowPhase.SYNTHESIZE if rounds <= 0 else WorkflowPhase.DEBATE_PEER
        )
        return {"phase": next_phase}

    def _debate_peer_node(self, state: MarketInsightState) -> dict[str, Any]:
        """
        同行评审节点 (Round 1)

        配对 A: Trend Scout ↔ Competitor Analyst
        配对 B: Regulation Checker ↔ Social Sentinel

        每个配对双向进行：
        1. A 质疑 B → B 回应 → A 确认/追问
        2. B 质疑 A → A 回应 → B 确认/追问
        """
        writer = get_stream_writer()

        writer(
            {
                "event": "debate_round_start",
                "round_number": 1,
                "debate_type": "peer_review",
                "pairs": [list(pair) for pair in DEBATE_PEER_PAIRS],
                "timestamp": datetime.now().isoformat(),
            }
        )

        logger.info("开始 Round 1: 同行评审")

        exchanges = []
        results_map = {r.agent_name: r for r in state.get("agent_results", [])}

        for pair in DEBATE_PEER_PAIRS:
            agent_a, agent_b = pair

            # 双向质疑
            for challenger, responder in [(agent_a, agent_b), (agent_b, agent_a)]:
                exchange = self._execute_debate_exchange(
                    state=state,
                    writer=writer,
                    round_number=1,
                    debate_type=DebateType.PEER_REVIEW,
                    challenger=challenger,
                    responder=responder,
                    results_map=results_map,
                )
                if exchange:
                    exchanges.append(exchange)

        writer(
            {
                "event": "debate_round_end",
                "round_number": 1,
                "debate_type": "peer_review",
                "exchanges_count": len(exchanges),
                "timestamp": datetime.now().isoformat(),
            }
        )

        return {
            "current_debate_round": 1,
            "current_debate_type": DebateType.PEER_REVIEW,
            "debate_exchanges": exchanges,
            "phase": WorkflowPhase.SYNTHESIZE
            if self._normalize_debate_rounds(state.get("debate_rounds", 0)) <= 1
            else WorkflowPhase.DEBATE_REDTEAM,
        }

    def _debate_redteam_node(self, state: MarketInsightState) -> dict[str, Any]:
        """
        红队审查节点 (Round 2)

        DeepSeek 红队逐一审查 4 个 Worker Agent
        """
        writer = get_stream_writer()

        writer(
            {
                "event": "debate_round_start",
                "round_number": 2,
                "debate_type": "red_team",
                "targets": DEBATE_REDTEAM_TARGETS,
                "timestamp": datetime.now().isoformat(),
            }
        )

        logger.info("开始 Round 2: 红队审查")

        exchanges = []
        results_map = {r.agent_name: r for r in state.get("agent_results", [])}

        for target_agent in DEBATE_REDTEAM_TARGETS:
            exchange = self._execute_debate_exchange(
                state=state,
                writer=writer,
                round_number=2,
                debate_type=DebateType.RED_TEAM,
                challenger=AGENT_DEBATE_CHALLENGER,
                responder=target_agent,
                results_map=results_map,
            )
            if exchange:
                exchanges.append(exchange)

        writer(
            {
                "event": "debate_round_end",
                "round_number": 2,
                "debate_type": "red_team",
                "exchanges_count": len(exchanges),
                "timestamp": datetime.now().isoformat(),
            }
        )

        return {
            "current_debate_round": 2,
            "current_debate_type": DebateType.RED_TEAM,
            "debate_exchanges": exchanges,
            "phase": WorkflowPhase.SYNTHESIZE,
        }

    def _execute_debate_exchange(
        self,
        state: MarketInsightState,
        writer: Callable,
        round_number: int,
        debate_type: DebateType,
        challenger: str,
        responder: str,
        results_map: dict[str, AgentResult],
    ) -> Optional[DebateExchange]:
        """
        执行单次辩论交换

        流程：质疑 → 回应 → (可选) 确认/追问
        """
        if not self.agent_factory:
            # 无 agent_factory 时返回占位结果
            return DebateExchange(
                round_number=round_number,
                debate_type=debate_type,
                challenger=challenger,
                responder=responder,
                challenge_content=f"[{challenger}] 质疑占位内容",
                response_content=f"[{responder}] 回应占位内容",
                followup_content=f"[{challenger}] 确认占位"
                if state.get("enable_followup")
                else None,
                revised=False,
            )

        max_attempts = max(1, int(state.get("retry_max_attempts", 1)))
        backoff_ms = max(0, int(state.get("retry_backoff_ms", 0)))
        degrade_mode = self._resolve_degrade_mode(state.get("degrade_mode", "partial"))

        for attempt in range(1, max_attempts + 1):
            try:
                from agents.debate import ChallengerAgent

                # 获取被质疑的内容
                responder_result = results_map.get(responder)
                if not responder_result or not responder_result.content:
                    return None

                # === Step 1: 质疑 ===
                writer(
                    {
                        "event": "agent_challenge",
                        "round_number": round_number,
                        "from_agent": challenger,
                        "to_agent": responder,
                        "attempt": attempt,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

                if debate_type == DebateType.PEER_REVIEW:
                    # 同行评审：由对方 Agent 发起质疑
                    challenge_agent = self.agent_factory(challenger)
                    # 构建质疑 prompt
                    challenge_prompt = self._build_peer_challenge_prompt(
                        challenger, responder, responder_result.content
                    )
                else:
                    # 红队审查：由 ChallengerAgent 发起
                    challenge_agent = self.agent_factory(AGENT_DEBATE_CHALLENGER)
                    if isinstance(challenge_agent, ChallengerAgent):
                        challenge_agent.challenge_mode = "redteam"
                        challenge_agent.set_challenge_context(
                            target_agent=responder,
                            target_content=responder_result.content,
                        )
                    challenge_prompt = None  # 使用 Agent 内置 prompt

                # 执行质疑
                challenge_content = self._execute_agent_call(
                    agent=challenge_agent,
                    state=state,
                    custom_prompt=challenge_prompt,
                    writer=writer,
                    event_prefix="challenge",
                    emit_chunks=False,
                )

                writer(
                    {
                        "event": "agent_challenge_end",
                        "round_number": round_number,
                        "from_agent": challenger,
                        "to_agent": responder,
                        "challenge_content": challenge_content,
                        "content": challenge_content,
                        "content_preview": challenge_content[:200]
                        if challenge_content
                        else "",
                        "attempt": attempt,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

                # === Step 2: 回应 ===
                writer(
                    {
                        "event": "agent_respond",
                        "round_number": round_number,
                        "from_agent": responder,
                        "to_agent": challenger,
                        "attempt": attempt,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

                responder_agent = self.agent_factory(responder)
                response_prompt = self._build_response_prompt(
                    responder, challenge_content, responder_result.content
                )

                response_content = self._execute_agent_call(
                    agent=responder_agent,
                    state=state,
                    custom_prompt=response_prompt,
                    writer=writer,
                    event_prefix="respond",
                    emit_chunks=False,
                )

                revised = ("修订" in (response_content or "")) or (
                    "修改" in (response_content or "")
                )

                writer(
                    {
                        "event": "agent_respond_end",
                        "round_number": round_number,
                        "from_agent": responder,
                        "to_agent": challenger,
                        "response_content": response_content,
                        "content": response_content,
                        "revised": revised,
                        "content_preview": response_content[:200]
                        if response_content
                        else "",
                        "attempt": attempt,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

                # === Step 3: 二次确认/追问 (可选) ===
                followup_content = None
                if state.get("enable_followup", True):
                    writer(
                        {
                            "event": "agent_followup",
                            "round_number": round_number,
                            "from_agent": challenger,
                            "to_agent": responder,
                            "attempt": attempt,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                    followup_prompt = self._build_followup_prompt(
                        challenger, challenge_content, response_content
                    )

                    # 使用同一个质疑 Agent 进行追问
                    followup_content = self._execute_agent_call(
                        agent=challenge_agent,
                        state=state,
                        custom_prompt=followup_prompt,
                        writer=writer,
                        event_prefix="followup",
                        emit_chunks=False,
                    )

                    writer(
                        {
                            "event": "agent_followup_end",
                            "round_number": round_number,
                            "from_agent": challenger,
                            "to_agent": responder,
                            "followup_content": followup_content,
                            "content": followup_content,
                            "content_preview": followup_content[:200]
                            if followup_content
                            else "",
                            "attempt": attempt,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                return DebateExchange(
                    round_number=round_number,
                    debate_type=debate_type,
                    challenger=challenger,
                    responder=responder,
                    challenge_content=challenge_content or "",
                    response_content=response_content or "",
                    followup_content=followup_content,
                    revised=revised,
                )

            except Exception as e:
                err = str(e)
                exchange_id = f"r{round_number}:{challenger}->{responder}"
                if attempt < max_attempts:
                    delay_ms = self._compute_backoff_ms(
                        backoff_ms, attempt, jitter_key=exchange_id
                    )
                    self._emit_retry_event(
                        writer=writer,
                        target_type="debate_exchange",
                        target_id=exchange_id,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        error=err,
                        backoff_ms=delay_ms,
                    )
                    self._sleep_backoff(delay_ms)
                    continue

                logger.error(f"辩论交换执行失败: {challenger} -> {responder}: {err}")
                if degrade_mode == "fail":
                    raise
                if degrade_mode == "partial":
                    return DebateExchange(
                        round_number=round_number,
                        debate_type=debate_type,
                        challenger=challenger,
                        responder=responder,
                        challenge_content="",
                        response_content="",
                        followup_content=f"[降级] 辩论交换失败: {err}",
                        revised=False,
                    )
                return None

        return None

    def _execute_agent_call(
        self,
        agent,
        state: MarketInsightState,
        custom_prompt: Optional[str],
        writer: Callable,
        event_prefix: str,
        emit_chunks: bool = True,
    ) -> str:
        """执行单次 Agent 调用"""
        from agents.base import AgentContext

        context = AgentContext(
            session_id=state["session_id"],
            profile=state["user_profile"],
            other_agent_outputs=[],
            debate_round=state.get("current_debate_round", 0),
        )

        if custom_prompt:
            messages = [
                {"role": "system", "content": agent.get_system_prompt(context)},
                {"role": "user", "content": custom_prompt},
            ]
        else:
            messages = [
                {"role": "system", "content": agent.get_system_prompt(context)},
                {"role": "user", "content": agent.get_user_prompt(context)},
            ]

        content_parts = []

        from core.ark_client import StreamEventType

        # 统一由工作流开关控制是否允许联网搜索
        effective_websearch = bool(getattr(agent, "use_websearch", False)) and bool(
            state.get("enable_websearch", False)
        )

        try:
            with self._acquire_ark_slot():
                for event in agent.ark_client.create_response_stream_v2(
                    messages=messages,
                    model=agent.model,
                    use_websearch=effective_websearch,
                    websearch_limit=getattr(agent, "websearch_limit", 0),
                    thinking_mode=getattr(agent, "thinking_mode", None),
                ):
                    if event.type == StreamEventType.OUTPUT_DELTA and event.content:
                        if emit_chunks:
                            writer(
                                {
                                    "event": f"{event_prefix}_chunk",
                                    "agent": agent.name,
                                    "content": event.content,
                                }
                            )
                        content_parts.append(event.content)
                    elif event.type == StreamEventType.SEARCH_START:
                        writer(
                            {
                                "event": "tool_start",
                                "tool": "web_search",
                                "agent": agent.name,
                                "context": event_prefix,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    elif event.type == StreamEventType.SEARCH_COMPLETE:
                        meta = event.metadata or {}
                        writer(
                            {
                                "event": "tool_end",
                                "tool": "web_search",
                                "agent": agent.name,
                                "context": event_prefix,
                                "sources_count": meta.get("sources_count", 0),
                                "timestamp": datetime.now().isoformat(),
                            }
                        )

            self._record_ark_outcome(success=True, error=None, writer=writer)
            return "".join(content_parts)
        except Exception as e:
            self._record_ark_outcome(success=False, error=str(e), writer=writer)
            raise

    def _build_peer_challenge_prompt(
        self, challenger: str, responder: str, responder_content: str
    ) -> str:
        """构建同行评审质疑 prompt"""
        agent_names = {
            "trend_scout": "趋势侦察员",
            "competitor_analyst": "竞争分析师",
            "regulation_checker": "法规检查员",
            "social_sentinel": "社媒哨兵",
        }

        return f"""## 同行评审任务

你是 **{agent_names.get(challenger, challenger)}**，请对 **{agent_names.get(responder, responder)}** 的分析报告进行专业审查。

### 被审查报告

{responder_content}

### 审查要求
1. 从你的专业视角出发，审查这份报告
2. 找出 2-4 个最值得关注的问题
3. 指出可能与你的分析存在矛盾的地方
4. 给出具体的改进建议

请开始审查并提出你的质疑："""

    def _build_response_prompt(
        self, responder: str, challenge_content: str, original_content: str
    ) -> str:
        """构建回应 prompt"""
        return f"""## 回应质疑

你收到了以下质疑，请认真回应：

### 你的原始分析
{original_content[:1000]}...

### 质疑内容
{challenge_content}

### 回应要求
1. **承认问题**：如果质疑有道理，坦诚承认并说明如何改进
2. **澄清误解**：如果质疑存在误解，礼貌地澄清
3. **补充论据**：如果有额外证据支持你的观点，请补充
4. **修订结论**：如果需要修改结论，明确说明修改内容

请开始回应："""

    def _build_followup_prompt(
        self, challenger: str, challenge_content: str, response_content: str
    ) -> str:
        """构建二次追问 prompt"""
        return f"""## 二次确认

你之前提出了质疑，对方已经回应。请评估回应是否充分。

### 你的原始质疑
{challenge_content[:500]}...

### 对方的回应
{response_content}

### 确认要求
1. 如果回应充分，表示接受并结束讨论
2. 如果回应不充分，提出追问（限 1-2 个点）
3. 简洁回复，不要重复已说过的内容

请进行确认（限 100-200 字）："""

    def _synthesizer_node(self, state: MarketInsightState) -> dict[str, Any]:
        """综合器节点：整合所有结果生成最终报告"""
        writer = get_stream_writer()
        start_time = time.time()

        writer(
            {
                "event": "agent_start",
                "agent": self.SYNTHESIZER,
                "timestamp": datetime.now().isoformat(),
            }
        )

        results = state.get("agent_results", [])
        debates = state.get("debate_exchanges", [])
        max_attempts = max(1, int(state.get("retry_max_attempts", 1)))
        backoff_ms = max(0, int(state.get("retry_backoff_ms", 0)))
        degrade_mode = self._resolve_degrade_mode(state.get("degrade_mode", "partial"))

        synthesized_report: str = ""
        synthesizer_status = "completed"
        fallback_reason: Optional[str] = None
        has_worker_content = any(r.content for r in results)

        if self.agent_factory and has_worker_content:
            for attempt in range(1, max_attempts + 1):
                try:
                    from agents.base import AgentContext, AgentOutput

                    # 构建综合分析师上下文
                    other_outputs = [
                        AgentOutput(
                            agent_name=r.agent_name,
                            content=r.content,
                            sources=r.sources,
                            thinking=r.thinking,
                        )
                        for r in results
                        if r.content
                    ]

                    context = AgentContext(
                        session_id=state["session_id"],
                        profile=state["user_profile"],
                        other_agent_outputs=other_outputs,
                        debate_round=state.get("current_debate_round", 0),
                        shared_memory={
                            "debate_history": [d.to_dict() for d in debates]
                        },
                    )

                    synthesizer = self.agent_factory(AGENT_SYNTHESIZER)

                    messages = [
                        {
                            "role": "system",
                            "content": synthesizer.get_system_prompt(context),
                        },
                        {
                            "role": "user",
                            "content": synthesizer.get_user_prompt(context),
                        },
                    ]

                    from core.ark_client import StreamEventType

                    content_parts = []
                    with self._acquire_ark_slot():
                        for event in synthesizer.ark_client.create_response_stream_v2(
                            messages=messages,
                            model=synthesizer.model,
                            use_websearch=False,
                            thinking_mode=getattr(synthesizer, "thinking_mode", None),
                        ):
                            if (
                                event.type == StreamEventType.OUTPUT_DELTA
                                and event.content
                            ):
                                writer(
                                    {
                                        "event": "agent_chunk",
                                        "agent": self.SYNTHESIZER,
                                        "content": event.content,
                                    }
                                )
                                content_parts.append(event.content)
                            elif (
                                event.type == StreamEventType.THINKING_DELTA
                                and event.content
                            ):
                                writer(
                                    {
                                        "event": "agent_thinking",
                                        "agent": self.SYNTHESIZER,
                                        "content": event.content,
                                    }
                                )

                    synthesized_report = "".join(content_parts)
                    synthesized_report = synthesizer.post_process(
                        synthesized_report, context
                    )
                    self._record_ark_outcome(success=True, error=None, writer=writer)
                    break
                except Exception as e:
                    err = str(e)
                    self._record_ark_outcome(success=False, error=err, writer=writer)
                    if attempt < max_attempts:
                        delay_ms = self._compute_backoff_ms(
                            backoff_ms, attempt, jitter_key=self.SYNTHESIZER
                        )
                        self._emit_retry_event(
                            writer=writer,
                            target_type="agent",
                            target_id=self.SYNTHESIZER,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            error=err,
                            backoff_ms=delay_ms,
                        )
                        self._sleep_backoff(delay_ms)
                        continue

                    logger.error(f"综合报告生成失败: {err}")
                    if degrade_mode == "fail":
                        raise
                    fallback_reason = f"综合模型调用失败，已使用降级报告: {err}"
                    synthesizer_status = "degraded"
                    writer(
                        {
                            "event": "agent_error",
                            "agent": self.SYNTHESIZER,
                            "error": err,
                            "degrade_mode": degrade_mode,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    synthesized_report = self._generate_fallback_report(
                        results, debates
                    )
                    break
        elif self.agent_factory and not has_worker_content:
            fallback_reason = "无可用的 Worker 输出，已跳过远程综合并生成降级报告"
            synthesizer_status = "degraded"
            writer(
                {
                    "event": "agent_error",
                    "agent": self.SYNTHESIZER,
                    "error": fallback_reason,
                    "degrade_mode": degrade_mode,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            synthesized_report = self._generate_fallback_report(results, debates)
        else:
            synthesized_report = self._generate_fallback_report(results, debates)

        generated_at = datetime.now().isoformat()
        try:
            evidence_pack = build_evidence_pack(
                session_id=state["session_id"],
                profile=state.get("user_profile", {}),
                agent_results=results,
                debate_exchanges=debates,
                final_report=synthesized_report,
                generated_at=generated_at,
            )
        except Exception as e:
            logger.warning(f"Evidence Pack 生成失败，将回退到最小结构: {e}")
            evidence_pack = {
                "version": "phase3.v1",
                "session_id": state.get("session_id"),
                "generated_at": generated_at,
                "claims": [],
                "sources": [],
                "traceability": [],
                "stats": {"claims_count": 0, "sources_count": 0, "debate_count": 0},
            }

        try:
            memory_snapshot = build_memory_snapshot(
                session_id=state["session_id"],
                profile=state.get("user_profile", {}),
                agent_results=results,
                debate_exchanges=debates,
                final_report=synthesized_report,
                generated_at=generated_at,
            )
        except Exception as e:
            logger.warning(f"轻量记忆快照生成失败，将回退到最小结构: {e}")
            memory_snapshot = {
                "version": "phase3.memory.v1",
                "session_id": state.get("session_id"),
                "generated_at": generated_at,
                "summary": "",
                "entities": {},
                "agent_highlights": [],
                "debate_focus": [],
                "action_items": [],
                "risk_items": [],
            }

        report_html_url: Optional[str] = None
        try:
            report_path = write_html_report(
                session_id=state["session_id"],
                report_markdown=synthesized_report,
                profile=state.get("user_profile", {}),
            )
            if report_path:
                report_html_url = (
                    f"/api/v2/market-insight/report/{state['session_id']}.html"
                )
        except Exception as e:
            logger.warning(f"HTML 报告生成失败: {e}")

        duration_ms = int((time.time() - start_time) * 1000)

        writer(
            {
                "event": "agent_end",
                "agent": self.SYNTHESIZER,
                "status": synthesizer_status,
                "error": fallback_reason,
                "duration_ms": duration_ms,
                "timestamp": datetime.now().isoformat(),
            }
        )

        writer(
            {
                "event": "orchestrator_end",
                "session_id": state["session_id"],
                "final_report": synthesized_report,
                "report_html_url": report_html_url,
                "evidence_pack": evidence_pack,
                "memory_snapshot": memory_snapshot,
                "timestamp": datetime.now().isoformat(),
            }
        )

        return {
            "synthesized_report": synthesized_report,
            "report_html_url": report_html_url,
            "evidence_pack": evidence_pack,
            "memory_snapshot": memory_snapshot,
            "phase": WorkflowPhase.COMPLETE,
            "completed_at": datetime.now(),
        }

    def _generate_fallback_report(
        self, results: list[AgentResult], debates: list[DebateExchange]
    ) -> str:
        """生成备用报告（无 LLM 时使用）"""
        report_parts = ["# 市场洞察报告\n"]
        success_count = 0

        for result in results:
            if result.content:
                success_count += 1
                report_parts.append(f"\n## {result.agent_name}\n")
                report_parts.append(result.content)

        failed_results = [r for r in results if not r.content and r.error]
        if failed_results:
            report_parts.append("\n## 采集异常记录\n")
            for r in failed_results:
                report_parts.append(f"- {r.agent_name}: {r.error}\n")

        if success_count == 0:
            report_parts.append(
                "\n## 说明\n当前会话未获得可用的上游模型输出，已返回降级报告。"
            )

        if debates:
            report_parts.append("\n## 辩论总结\n")
            for exchange in debates:
                report_parts.append(
                    f"- 第 {exchange.round_number} 轮 ({exchange.debate_type.value}): "
                    f"{exchange.challenger} → {exchange.responder}\n"
                )

        return "".join(report_parts)


# ============================================
# 工厂函数
# ============================================


def create_market_insight_engine(
    agent_factory: Optional[Callable[[str], Any]] = None,
    debate_rounds: int = settings.default_debate_rounds,
    enable_followup: bool = True,
    retry_max_attempts: int = 2,
    retry_backoff_ms: int = 300,
    degrade_mode: Literal["skip", "partial", "fail"] = "partial",
    use_checkpointer: bool = True,
) -> MarketInsightGraphEngine:
    """
    创建市场洞察图引擎

    Args:
        agent_factory: Agent 工厂函数
        debate_rounds: 辩论轮数
        enable_followup: 是否启用二次回应
        retry_max_attempts: 节点最大重试次数
        retry_backoff_ms: 重试退避起始毫秒（指数退避）
        degrade_mode: 重试耗尽后的降级策略（skip/partial/fail）
        use_checkpointer: 是否使用检查点

    Returns:
        MarketInsightGraphEngine: 编译好的图引擎
    """
    engine = MarketInsightGraphEngine(
        agent_factory=agent_factory,
        debate_rounds=debate_rounds,
        enable_followup=enable_followup,
        retry_max_attempts=retry_max_attempts,
        retry_backoff_ms=retry_backoff_ms,
        degrade_mode=degrade_mode,
    )
    engine.build()

    checkpointer = MemorySaver() if use_checkpointer else None
    engine.compile(checkpointer=checkpointer)

    return engine
