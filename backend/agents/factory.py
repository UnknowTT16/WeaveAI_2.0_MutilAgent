# backend/agents/factory.py
"""
Agent 工厂模块

提供统一的 Agent 创建和获取接口
"""

from typing import Optional, Callable, Type, Dict

from core.config import (
    AGENT_TREND_SCOUT,
    AGENT_COMPETITOR_ANALYST,
    AGENT_REGULATION_CHECKER,
    AGENT_SOCIAL_SENTINEL,
    AGENT_SYNTHESIZER,
    AGENT_DEBATE_CHALLENGER,
)
from core.ark_client import ArkClientWrapper, get_ark_client
from agents.base import BaseAgent


# ============================================
# Agent 注册表
# ============================================

# 延迟导入，避免循环依赖
_agent_registry: Dict[str, Type[BaseAgent]] = {}
_registry_initialized = False


def _init_registry():
    """初始化 Agent 注册表（延迟加载）"""
    global _registry_initialized, _agent_registry
    
    if _registry_initialized:
        return
    
    # 导入所有 Agent 类
    from agents.market import (
        TrendScoutAgent,
        CompetitorAnalystAgent,
        RegulationCheckerAgent,
        SocialSentinelAgent,
        SynthesizerAgent,
    )
    from agents.debate import ChallengerAgent
    
    _agent_registry = {
        AGENT_TREND_SCOUT: TrendScoutAgent,
        AGENT_COMPETITOR_ANALYST: CompetitorAnalystAgent,
        AGENT_REGULATION_CHECKER: RegulationCheckerAgent,
        AGENT_SOCIAL_SENTINEL: SocialSentinelAgent,
        AGENT_SYNTHESIZER: SynthesizerAgent,
        AGENT_DEBATE_CHALLENGER: ChallengerAgent,
    }
    
    _registry_initialized = True


def get_agent_class(agent_name: str) -> Optional[Type[BaseAgent]]:
    """
    获取 Agent 类
    
    Args:
        agent_name: Agent 名称
        
    Returns:
        Agent 类，如果不存在返回 None
    """
    _init_registry()
    return _agent_registry.get(agent_name)


def create_agent(
    agent_name: str,
    ark_client: Optional[ArkClientWrapper] = None,
    stream_writer: Optional[Callable[[dict], None]] = None,
    **kwargs
) -> Optional[BaseAgent]:
    """
    创建 Agent 实例
    
    Args:
        agent_name: Agent 名称
        ark_client: Ark 客户端实例，不传则使用默认单例
        stream_writer: LangGraph 流式写入器
        **kwargs: 其他传递给 Agent 构造函数的参数
        
    Returns:
        Agent 实例，如果不存在返回 None
    """
    agent_class = get_agent_class(agent_name)
    
    if agent_class is None:
        return None
    
    # 使用默认 Ark 客户端
    ark_client = ark_client or get_ark_client()
    
    return agent_class(
        ark_client=ark_client,
        stream_writer=stream_writer,
        **kwargs
    )


def list_agents() -> list[str]:
    """
    获取所有已注册的 Agent 名称
    
    Returns:
        Agent 名称列表
    """
    _init_registry()
    return list(_agent_registry.keys())


def get_worker_agents() -> list[str]:
    """
    获取所有 Worker Agent 名称
    
    Returns:
        Worker Agent 名称列表
    """
    return [
        AGENT_TREND_SCOUT,
        AGENT_COMPETITOR_ANALYST,
        AGENT_REGULATION_CHECKER,
        AGENT_SOCIAL_SENTINEL,
    ]


def get_debate_agents() -> list[str]:
    """
    获取所有辩论相关 Agent 名称
    
    Returns:
        辩论 Agent 名称列表
    """
    return [AGENT_DEBATE_CHALLENGER]


# ============================================
# 工厂函数 (用于 LangGraph)
# ============================================

def agent_factory_for_graph(
    ark_client: Optional[ArkClientWrapper] = None
) -> Callable[[str], BaseAgent]:
    """
    创建用于 LangGraph 的 Agent 工厂函数
    
    Args:
        ark_client: Ark 客户端实例
        
    Returns:
        工厂函数，接收 agent_name 返回 Agent 实例
    """
    client = ark_client or get_ark_client()
    
    def factory(agent_name: str) -> BaseAgent:
        agent = create_agent(agent_name, ark_client=client)
        if agent is None:
            raise ValueError(f"未知的 Agent: {agent_name}")
        return agent
    
    return factory


# ============================================
# 辅助函数
# ============================================

def get_agent_display_name(agent_name: str) -> str:
    """
    获取 Agent 的显示名称（中文）
    
    Args:
        agent_name: Agent 名称
        
    Returns:
        中文显示名称
    """
    display_names = {
        AGENT_TREND_SCOUT: "趋势侦察员",
        AGENT_COMPETITOR_ANALYST: "竞争分析师",
        AGENT_REGULATION_CHECKER: "法规检查员",
        AGENT_SOCIAL_SENTINEL: "社媒哨兵",
        AGENT_SYNTHESIZER: "综合分析师",
        AGENT_DEBATE_CHALLENGER: "红队审查官",
    }
    return display_names.get(agent_name, agent_name)


def get_agent_description(agent_name: str) -> str:
    """
    获取 Agent 的描述
    
    Args:
        agent_name: Agent 名称
        
    Returns:
        Agent 描述
    """
    descriptions = {
        AGENT_TREND_SCOUT: "发现市场新兴趋势和机会窗口",
        AGENT_COMPETITOR_ANALYST: "竞争格局分析和竞品研究",
        AGENT_REGULATION_CHECKER: "合规风险审查和政策解读",
        AGENT_SOCIAL_SENTINEL: "舆情监测和消费者洞察",
        AGENT_SYNTHESIZER: "整合多维分析，形成最终报告",
        AGENT_DEBATE_CHALLENGER: "批判性审查和质疑",
    }
    return descriptions.get(agent_name, "未知 Agent")
