# backend/routers/v2/__init__.py
"""
v2 API 路由

包含 Supervisor-Worker + 多轮辩论 架构的市场洞察 API
"""

from fastapi import APIRouter

from .market_insight import router as market_insight_router

router = APIRouter(prefix="/api/v2", tags=["v2"])

# 注册子路由
router.include_router(market_insight_router)

__all__ = ["router"]
