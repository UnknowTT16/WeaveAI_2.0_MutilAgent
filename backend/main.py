# backend/main.py
"""
WeaveAI 2.0 后端入口

架构：Supervisor-Worker + 多轮辩论
技术栈：FastAPI + LangGraph + 火山引擎 Ark

专注 WeaveAI 2.0 (v2 API)
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# FastAPI 应用
# ============================================

app = FastAPI(
    title="WeaveAI Backend API",
    description="WeaveAI 2.0 - Supervisor-Worker + 多轮辩论 多 Agent 协作系统",
    version="2.0.0",
)

# ============================================
# CORS 配置
# ============================================

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://172.20.10.6:3000",
    "http://8.134.84.154:3000",
    "http://8.134.100.38:3000",
    "http://192.168.43.4:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# v2 API 路由 (WeaveAI 2.0 核心)
# ============================================

from routers.v2 import router as v2_router

app.include_router(v2_router)

# ============================================
# 健康检查
# ============================================


@app.get("/", tags=["General"])
def read_root():
    """根路由 - 健康检查"""
    return {
        "message": "Welcome to WeaveAI Backend!",
        "version": "2.0.0",
        "api": {
            "v2": "/api/v2/market-insight/health",
        },
    }


@app.get("/health", tags=["General"])
def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "v2_available": True,
    }
