# backend/database/client.py
"""
Supabase 客户端封装
"""

from typing import Optional, Any
from functools import lru_cache
import logging

from supabase import create_client, Client
from core.config import settings

logger = logging.getLogger(__name__)


class SupabaseClient:
    """
    Supabase 客户端封装
    
    提供数据库操作的统一接口
    """
    
    def __init__(self, client: Client):
        self._client = client
    
    @property
    def client(self) -> Client:
        """获取原始 Supabase 客户端"""
        return self._client
    
    # ============================================
    # Sessions 表操作
    # ============================================
    
    def create_session(self, session_data: dict[str, Any]) -> dict[str, Any]:
        """
        创建新会话
        
        Args:
            session_data: 会话数据
            
        Returns:
            dict: 创建的会话记录
        """
        result = self._client.table("sessions").insert(session_data).execute()
        return result.data[0] if result.data else {}
    
    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        """
        获取会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            dict | None: 会话记录
        """
        result = self._client.table("sessions").select("*").eq("id", session_id).execute()
        return result.data[0] if result.data else None
    
    def update_session(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """
        更新会话
        
        Args:
            session_id: 会话 ID
            updates: 更新字段
            
        Returns:
            dict: 更新后的会话记录
        """
        result = self._client.table("sessions").update(updates).eq("id", session_id).execute()
        return result.data[0] if result.data else {}
    
    def get_session_full(self, session_id: str) -> Optional[dict[str, Any]]:
        """
        获取会话完整数据 (包括 Agent 结果、辩论记录等)
        
        使用数据库函数获取
        """
        result = self._client.rpc("get_session_full", {"p_session_id": session_id}).execute()
        return result.data if result.data else None
    
    # ============================================
    # Agent Results 表操作
    # ============================================
    
    def create_agent_result(self, result_data: dict[str, Any]) -> dict[str, Any]:
        """创建 Agent 结果"""
        result = self._client.table("agent_results").insert(result_data).execute()
        return result.data[0] if result.data else {}
    
    def update_agent_result(self, result_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """更新 Agent 结果"""
        result = self._client.table("agent_results").update(updates).eq("id", result_id).execute()
        return result.data[0] if result.data else {}
    
    def get_session_agent_results(self, session_id: str) -> list[dict[str, Any]]:
        """获取会话的所有 Agent 结果"""
        result = self._client.table("agent_results").select("*").eq("session_id", session_id).execute()
        return result.data or []
    
    # ============================================
    # Debate Exchanges 表操作
    # ============================================
    
    def create_debate_exchange(self, exchange_data: dict[str, Any]) -> dict[str, Any]:
        """创建辩论交换记录"""
        result = self._client.table("debate_exchanges").insert(exchange_data).execute()
        return result.data[0] if result.data else {}
    
    def get_session_debates(self, session_id: str) -> list[dict[str, Any]]:
        """获取会话的所有辩论记录"""
        result = (
            self._client.table("debate_exchanges")
            .select("*")
            .eq("session_id", session_id)
            .order("round_number")
            .execute()
        )
        return result.data or []
    
    # ============================================
    # Workflow Events 表操作
    # ============================================
    
    def log_workflow_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """记录工作流事件"""
        result = self._client.table("workflow_events").insert(event_data).execute()
        return result.data[0] if result.data else {}
    
    def get_session_events(
        self, 
        session_id: str, 
        event_types: Optional[list[str]] = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        获取会话的工作流事件
        
        Args:
            session_id: 会话 ID
            event_types: 过滤的事件类型
            limit: 返回数量限制
        """
        query = (
            self._client.table("workflow_events")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        
        if event_types:
            query = query.in_("event_type", event_types)
        
        result = query.execute()
        return result.data or []
    
    # ============================================
    # Feedback 表操作
    # ============================================
    
    def create_feedback(self, feedback_data: dict[str, Any]) -> dict[str, Any]:
        """创建反馈"""
        result = self._client.table("feedback").insert(feedback_data).execute()
        return result.data[0] if result.data else {}
    
    def get_session_feedback(self, session_id: str) -> Optional[dict[str, Any]]:
        """获取会话反馈"""
        result = self._client.table("feedback").select("*").eq("session_id", session_id).execute()
        return result.data[0] if result.data else None


# ============================================
# 单例工厂
# ============================================

_supabase_client: Optional[SupabaseClient] = None


def get_supabase_client() -> Optional[SupabaseClient]:
    """
    获取 Supabase 客户端单例
    
    如果未配置 Supabase，返回 None
    """
    global _supabase_client
    
    if _supabase_client is not None:
        return _supabase_client
    
    if not settings.supabase_url or not settings.supabase_anon_key:
        logger.warning("Supabase 未配置，数据库功能不可用")
        return None
    
    try:
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        _supabase_client = SupabaseClient(client)
        logger.info("Supabase 客户端初始化成功")
        return _supabase_client
    except Exception as e:
        logger.error(f"Supabase 客户端初始化失败: {e}")
        return None
