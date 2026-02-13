// frontend/hooks/useStreamV2.js
/**
 * WeaveAI 2.0 流式 Hook
 * 处理 v2 API 的 SSE 事件流
 */

import { useCallback, useRef, useEffect } from 'react';
import { useWorkflowActions } from '../contexts/WorkflowContext';
import { API_ENDPOINTS } from '../lib/constants';

/**
 * v2 流式生成 Hook
 * 自动将 SSE 事件分发到 WorkflowContext
 */
export function useStreamV2() {
  const actions = useWorkflowActions();
  const abortControllerRef = useRef(null);

  const createSessionId = useCallback(() => {
    if (typeof globalThis !== 'undefined' && globalThis.crypto?.randomUUID) {
      return globalThis.crypto.randomUUID();
    }
    return `session_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  }, []);

  const hydrateFromStatus = useCallback(async (sessionId) => {
    if (!sessionId) return;
    try {
      const resp = await fetch(`${API_ENDPOINTS.MARKET_INSIGHT_STATUS}/${sessionId}`);
      if (!resp.ok) return;
      const data = await resp.json();
      actions.hydrateFromStatus(data);
    } catch (e) {
      console.warn('Failed to hydrate workflow from status API:', e);
    }
  }, [actions]);
  
  // 清理函数
  const cleanup = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);
  
  // 组件卸载时清理
  useEffect(() => {
    return cleanup;
  }, [cleanup]);
  
  /**
   * 开始流式生成
   * @param {Object} options
   * @param {Object} options.profile - 用户画像
   * @param {boolean} options.enableWebsearch - 是否启用 WebSearch
   * @param {number} options.debateRounds - 辩论轮数
   */
  const startStream = useCallback(async (options) => {
    const {
      profile,
      enableWebsearch = false,
      debateRounds = 2,
      retryMaxAttempts = 2,
      retryBackoffMs = 300,
      degradeMode = 'partial',
      sessionId: incomingSessionId,
    } = options;
    const sessionId = incomingSessionId || createSessionId();
    
    // 清理之前的连接
    cleanup();
    
    // 创建新的 AbortController
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    
    // 开始生成
    actions.startGeneration();
    actions.setSession(sessionId);
    
    try {
      // 调用 v2 API
      const response = await fetch(API_ENDPOINTS.MARKET_INSIGHT_STREAM, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: sessionId,
          profile,
          enable_websearch: enableWebsearch,
          debate_rounds: debateRounds,
          retry_max_attempts: retryMaxAttempts,
          retry_backoff_ms: retryBackoffMs,
          degrade_mode: degradeMode,
        }),
        signal: abortController.signal,
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `HTTP error: ${response.status}`);
      }
      
      if (!response.body) {
        throw new Error('Response body is null');
      }
      
      // 读取 SSE 流
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        // 按行解析 SSE 事件
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // 保留不完整的行
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim();
            if (data === '[DONE]') {
              actions.stopGeneration();
              continue;
            }
            
            try {
              const event = JSON.parse(data);
              // 使用 Context 的 SSE 事件处理器
              actions.handleSSEEvent(event);
            } catch (e) {
              console.warn('Failed to parse SSE event:', data, e);
            }
          }
        }
      }
      
      // 处理剩余的 buffer
      if (buffer.startsWith('data: ')) {
        const data = buffer.slice(6).trim();
        if (data && data !== '[DONE]') {
          try {
            const event = JSON.parse(data);
            actions.handleSSEEvent(event);
          } catch (e) {
            console.warn('Failed to parse final SSE event:', data, e);
          }
        }
      }
      
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('Stream aborted by user');
      } else {
        console.error('Stream error:', error);
        actions.setError(error.message);
        await hydrateFromStatus(sessionId);
      }
    } finally {
      abortControllerRef.current = null;
    }
  }, [actions, cleanup, createSessionId, hydrateFromStatus]);
  
  /**
   * 停止流式生成
   */
  const stopStream = useCallback(() => {
    cleanup();
    actions.stopGeneration();
  }, [cleanup, actions]);
  
  return {
    startStream,
    stopStream,
  };
}
