# backend/routers/__init__.py
"""
API 路由模块

- v2: WeaveAI 2.0 (Supervisor-Worker + 多轮辩论)
"""

from .v2 import router as v2_router

__all__ = ["v2_router"]
