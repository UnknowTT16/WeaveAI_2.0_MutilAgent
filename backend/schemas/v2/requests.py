# backend/schemas/v2/requests.py
"""
v2 API 请求模型
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """用户档案"""

    target_market: str = Field(
        ..., description="目标市场", examples=["Germany", "Japan"]
    )
    supply_chain: str = Field(
        ..., description="供应链/品类", examples=["Consumer Electronics"]
    )
    seller_type: str = Field(
        ..., description="卖家类型", examples=["Cross-border E-commerce"]
    )
    min_price: int = Field(default=0, ge=0, description="最低价格")
    max_price: int = Field(default=1000, ge=0, description="最高价格")


class CreateSessionRequest(BaseModel):
    """创建会话请求"""

    profile: UserProfile


class MarketInsightRequest(BaseModel):
    """市场洞察分析请求"""

    # session_id 在流式接口中可选：不传则由服务端生成
    session_id: Optional[str] = Field(default=None, description="会话 ID")

    # 用户画像（推荐直接传入；也可仅传 session_id 走后续存储/恢复逻辑）
    profile: Optional[UserProfile] = Field(default=None, description="用户画像")

    # 辩论轮数与二次回应控制
    debate_rounds: int = Field(
        default=2,
        ge=0,
        le=2,
        description="辩论轮数（0=跳过辩论，1=同行评审，2=同行+红队）",
    )
    enable_followup: bool = Field(default=True, description="是否启用二次回应")

    # 是否启用 web_search（会覆盖各 Agent 默认配置）
    enable_websearch: bool = Field(default=False, description="是否启用联网搜索")

    # 重试与降级策略
    retry_max_attempts: int = Field(
        default=2, ge=1, le=5, description="节点最大重试次数"
    )
    retry_backoff_ms: int = Field(
        default=300,
        ge=0,
        le=10000,
        description="重试退避起始毫秒（指数退避）",
    )
    degrade_mode: Literal["skip", "partial", "fail"] = Field(
        default="partial",
        description="重试耗尽后的降级策略",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "uuid-xxx",
                "profile": {
                    "target_market": "Germany",
                    "supply_chain": "Consumer Electronics",
                    "seller_type": "Cross-border E-commerce",
                    "min_price": 0,
                    "max_price": 1000,
                },
                "debate_rounds": 2,
                "enable_followup": True,
                "enable_websearch": True,
                "retry_max_attempts": 2,
                "retry_backoff_ms": 300,
                "degrade_mode": "partial",
            }
        }
