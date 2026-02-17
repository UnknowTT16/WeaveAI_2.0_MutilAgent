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
    if (!sessionId) return null;
    try {
      const resp = await fetch(`${API_ENDPOINTS.MARKET_INSIGHT_STATUS}/${sessionId}`);
      if (!resp.ok) return null;
      const data = await resp.json();
      actions.hydrateFromStatus(data);
      return data;
    } catch (e) {
      console.warn('Failed to hydrate workflow from status API:', e);
      return null;
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
      let sawOrchestratorEnd = false;
      let sawAnyEvent = false;

      const consumeSSEBlocks = (rawText) => {
        const normalized = rawText
          .replace(/\r\n/g, '\n')
          .replace(/\r/g, '\n');
        const blocks = normalized.split('\n\n');
        const rest = blocks.pop() || '';

        for (const rawBlock of blocks) {
          const block = rawBlock.trim();
          if (!block) continue;

          const dataLines = [];
          for (const rawLine of block.split('\n')) {
            const line = rawLine.trimStart();
            if (line.startsWith(':')) continue;
            if (line.startsWith('data:')) {
              dataLines.push(line.slice(5).trimStart());
            }
          }

          if (dataLines.length === 0) continue;

          const data = dataLines.join('\n').trim();
          if (!data) continue;

          if (data === '[DONE]') {
            sawOrchestratorEnd = true;
            continue;
          }

          try {
            const event = JSON.parse(data);
            sawAnyEvent = true;
            if (event.event === 'orchestrator_end') {
              sawOrchestratorEnd = true;
            }
            actions.handleSSEEvent(event);
          } catch (e) {
            console.warn('Failed to parse SSE event block:', data, e);
          }
        }

        return rest;
      };
      
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        buffer = consumeSSEBlocks(buffer);
      }

      // 处理最后一段（强制补一个空行分隔，确保最后一个 event 也被消费）
      buffer += decoder.decode();
      buffer = consumeSSEBlocks(`${buffer}\n\n`);

      if (!abortController.signal.aborted) {
        const statusPayload = await hydrateFromStatus(sessionId);
        const sessionStatus = statusPayload?.session?.status;
        if (!sawAnyEvent && !statusPayload) {
          actions.setError('流式连接已建立，但未收到有效事件。请检查后端日志或网络。');
        }
        if (sawOrchestratorEnd || sessionStatus !== 'running') {
          actions.stopGeneration();
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
