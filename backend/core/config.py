# backend/core/config.py
"""
应用配置：使用 Pydantic Settings 管理环境变量
"""

import os
from functools import lru_cache
from typing import Optional, Literal
from pydantic_settings import BaseSettings
from pydantic import Field
from enum import Enum


# ============================================
# 枚举定义
# ============================================


class ThinkingMode(str, Enum):
    """Thinking 模式枚举"""

    AUTO = "auto"  # 模型自动判断
    ENABLED = "enabled"  # 强制启用
    DISABLED = "disabled"  # 禁用


# ============================================
# Agent-Model 映射配置
# ============================================

# Agent 名称常量
AGENT_TREND_SCOUT = "trend_scout"
AGENT_COMPETITOR_ANALYST = "competitor_analyst"
AGENT_REGULATION_CHECKER = "regulation_checker"
AGENT_SOCIAL_SENTINEL = "social_sentinel"
AGENT_SYNTHESIZER = "synthesizer"
AGENT_DEBATE_CHALLENGER = "debate_challenger"

# Agent -> Model 映射 (基于用户确认的设计)
AGENT_MODEL_MAPPING: dict[str, str] = {
    # Worker Agents
    AGENT_TREND_SCOUT: "doubao-seed-2-0-pro-260215",  # 2.0旗舰 + 强联网 + 发散联想
    AGENT_COMPETITOR_ANALYST: "deepseek-v3-2-251201",  # 逻辑推理强 + 结构化分析
    AGENT_REGULATION_CHECKER: "kimi-k2-thinking-251104",  # 长文档阅读 + Thinking 模式
    AGENT_SOCIAL_SENTINEL: "doubao-seed-2-0-pro-260215",  # 2.0旗舰 + 中文语感 + 情感理解
    # Synthesizer
    AGENT_SYNTHESIZER: "kimi-k2-thinking-251104",  # 超长上下文 + 不丢细节
    # Debate Agent
    AGENT_DEBATE_CHALLENGER: "deepseek-v3-2-251201",  # 批判性思维 + 逻辑反驳
}

# Agent -> Thinking 模式映射
AGENT_THINKING_MODE: dict[str, ThinkingMode] = {
    # 采集型 Worker Agent 统一强制开启 thinking
    AGENT_TREND_SCOUT: ThinkingMode.ENABLED,
    AGENT_COMPETITOR_ANALYST: ThinkingMode.ENABLED,
    AGENT_REGULATION_CHECKER: ThinkingMode.ENABLED,  # Kimi K2 Thinking
    AGENT_SOCIAL_SENTINEL: ThinkingMode.ENABLED,
    AGENT_SYNTHESIZER: ThinkingMode.ENABLED,  # Kimi K2 Thinking
    AGENT_DEBATE_CHALLENGER: ThinkingMode.DISABLED,
}

# Agent -> WebSearch 配置
AGENT_WEBSEARCH_CONFIG: dict[str, dict] = {
    AGENT_TREND_SCOUT: {"enabled": True, "limit": 20},  # 趋势需要更多搜索
    AGENT_COMPETITOR_ANALYST: {"enabled": True, "limit": 15},
    AGENT_REGULATION_CHECKER: {"enabled": True, "limit": 15},
    AGENT_SOCIAL_SENTINEL: {"enabled": True, "limit": 20},  # 社媒需要更多搜索
    AGENT_SYNTHESIZER: {"enabled": False, "limit": 0},  # 综合器不需要搜索
    AGENT_DEBATE_CHALLENGER: {"enabled": False, "limit": 0},  # 辩论不需要搜索
}


# ============================================
# 辩论配对配置
# ============================================

# Round 1: 同行评审配对 (Worker 之间互相质疑)
DEBATE_PEER_PAIRS: list[tuple[str, str]] = [
    (AGENT_TREND_SCOUT, AGENT_COMPETITOR_ANALYST),  # 趋势 ↔ 竞品
    (AGENT_REGULATION_CHECKER, AGENT_SOCIAL_SENTINEL),  # 法规 ↔ 社媒
]

# Round 2: 红队审查 (DeepSeek 逐一审查所有 Worker)
DEBATE_REDTEAM_TARGETS: list[str] = [
    AGENT_TREND_SCOUT,
    AGENT_COMPETITOR_ANALYST,
    AGENT_REGULATION_CHECKER,
    AGENT_SOCIAL_SENTINEL,
]


class Settings(BaseSettings):
    """应用配置"""

    # ============================================
    # 火山引擎 Ark API 配置
    # ============================================
    # 说明：为了允许在未配置 Key 的情况下启动服务并访问健康检查，
    # 这里将 key 设为可选；真正调用模型时由 ArkClientWrapper 再做强校验。
    ark_api_key: Optional[str] = Field(default=None, alias="ARK_API_KEY")
    ark_base_url: str = Field(
        default="https://ark.cn-beijing.volces.com/api/v3", alias="ARK_BASE_URL"
    )
    ark_timeout_seconds: float = Field(default=120.0, alias="ARK_TIMEOUT_SECONDS")
    ark_connect_timeout_seconds: float = Field(
        default=20.0, alias="ARK_CONNECT_TIMEOUT_SECONDS"
    )
    ark_max_retries: int = Field(default=2, alias="ARK_MAX_RETRIES")

    # 默认模型 (支持 web_search 的模型)
    default_model: str = Field(default="doubao-seed-1-6-250615", alias="DEFAULT_MODEL")

    # 备选模型列表 (都支持 web_search)
    supported_models: list[str] = [
        "doubao-seed-2-0-pro-260215",
        "doubao-seed-1-6-250615",
        "deepseek-v3-2-251201",
        "deepseek-v3-1-terminus",
        "deepseek-v3-1-250821",
        "kimi-k2-thinking-251104",
        "kimi-k2-250905",
    ]

    # ============================================
    # Supabase 配置
    # ============================================
    supabase_url: Optional[str] = Field(default=None, alias="SUPABASE_URL")
    supabase_anon_key: Optional[str] = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: Optional[str] = Field(
        default=None, alias="SUPABASE_SERVICE_ROLE_KEY"
    )

    # ============================================
    # 应用配置
    # ============================================
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # 辩论配置
    default_debate_rounds: int = Field(default=2, alias="DEFAULT_DEBATE_ROUNDS")
    max_debate_rounds: int = Field(default=4, alias="MAX_DEBATE_ROUNDS")

    # 二次回应配置 (质疑 → 回应 → 确认/追问)
    enable_followup_response: bool = Field(
        default=True, alias="ENABLE_FOLLOWUP_RESPONSE"
    )

    # 工具限流配置
    tool_rate_limit_qps: int = Field(default=5, alias="TOOL_RATE_LIMIT_QPS")

    # web_search 配置
    web_search_limit: int = Field(default=15, alias="WEB_SEARCH_LIMIT")

    # PDF 导出配置
    chrome_path: Optional[str] = Field(default=None, alias="CHROME_PATH")

    # ============================================
    # 辅助方法
    # ============================================

    def get_agent_model(self, agent_name: str) -> str:
        """获取 Agent 对应的模型"""
        return AGENT_MODEL_MAPPING.get(agent_name, self.default_model)

    def get_agent_thinking_mode(self, agent_name: str) -> ThinkingMode:
        """获取 Agent 的 Thinking 模式"""
        return AGENT_THINKING_MODE.get(agent_name, ThinkingMode.DISABLED)

    def get_agent_websearch_config(self, agent_name: str) -> dict:
        """获取 Agent 的 WebSearch 配置"""
        return AGENT_WEBSEARCH_CONFIG.get(
            agent_name, {"enabled": True, "limit": self.web_search_limit}
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # 忽略未定义的环境变量


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


# 导出配置实例
settings = get_settings()
