// frontend/hooks/useStreamV2.js
/**
 * WeaveAI 2.0 流式 Hook
 * 处理 v2 API 的 SSE 事件流
 */

import { useCallback, useRef, useEffect } from 'react';
import { useWorkflowActions } from '../contexts/WorkflowContext';
import { API_ENDPOINTS } from '../lib/constants';

const STREAM_IDLE_TIMEOUT_MS = 20000;
const STATUS_RECOVERY_TIMEOUT_MS = 90000;
const STATUS_RECOVERY_INTERVAL_MS = 3000;
const TERMINAL_SESSION_STATUSES = new Set(['completed', 'failed', 'cancelled']);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function createUuidFallback() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (token) => {
    const rand = Math.floor(Math.random() * 16);
    const value = token === 'x' ? rand : ((rand & 0x3) | 0x8);
    return value.toString(16);
  });
}

function isTerminalStatus(status) {
  return TERMINAL_SESSION_STATUSES.has(String(status || '').toLowerCase());
}

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
    return createUuidFallback();
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

  const recoverFromStatus = useCallback(async (sessionId, reason = 'stream_interrupted') => {
    if (!sessionId) {
      return { recovered: false, status: null, reason };
    }

    const startedAt = Date.now();
    const deadline = startedAt + STATUS_RECOVERY_TIMEOUT_MS;
    let latestPayload = null;
    let attempts = 0;

    actions.setRecoveryState({
      mode: 'recovering',
      reason,
      message: '检测到连接波动，正在通过状态接口自动恢复。',
      startedAt,
      deadlineAt: deadline,
      attempts: 0,
      lastSessionStatus: null,
    });

    while (Date.now() <= deadline) {
      attempts += 1;
      latestPayload = await hydrateFromStatus(sessionId);
      const status = latestPayload?.session?.status || null;
      actions.setRecoveryState({
        mode: 'recovering',
        reason,
        message: '恢复进行中：持续轮询状态接口。',
        startedAt,
        deadlineAt: deadline,
        attempts,
        lastSessionStatus: status,
      });

      if (isTerminalStatus(status)) {
        actions.stopGeneration();
        actions.setRecoveryState({
          mode: 'recovered',
          reason,
          message: '已通过状态接口恢复展示，流程结果已同步。',
          startedAt,
          deadlineAt: deadline,
          attempts,
          lastSessionStatus: status,
        });
        return {
          recovered: true,
          status,
          payload: latestPayload,
          reason,
          attempts,
        };
      }
      await sleep(STATUS_RECOVERY_INTERVAL_MS);
    }

    const finalStatus = latestPayload?.session?.status || null;
    if (isTerminalStatus(finalStatus)) {
      actions.stopGeneration();
      actions.setRecoveryState({
        mode: 'recovered',
        reason,
        message: '恢复窗口结束前已同步到终态结果。',
        startedAt,
        deadlineAt: deadline,
        attempts,
        lastSessionStatus: finalStatus,
      });
      return {
        recovered: true,
        status: finalStatus,
        payload: latestPayload,
        reason,
        attempts,
      };
    }

    actions.setRecoveryState({
      mode: 'timeout',
      reason,
      message: '90 秒自动恢复窗口已结束，请手动重试。',
      startedAt,
      deadlineAt: deadline,
      attempts,
      lastSessionStatus: finalStatus,
    });

    return {
      recovered: false,
      status: finalStatus,
      payload: latestPayload,
      reason,
      attempts,
    };
  }, [actions, hydrateFromStatus]);

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
      enableFollowup = true,
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
    actions.clearRecoveryState();
    
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
          enable_followup: enableFollowup,
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

      const readWithTimeout = async () => {
        let timeoutId = null;
        try {
          return await Promise.race([
            reader.read().then((result) => ({ type: 'read', result })).catch((error) => ({ type: 'read_error', error })),
            new Promise((resolve) => {
              timeoutId = setTimeout(() => resolve({ type: 'idle_timeout' }), STREAM_IDLE_TIMEOUT_MS);
            }),
          ]);
        } finally {
          if (timeoutId) clearTimeout(timeoutId);
        }
      };

      while (true) {
        const outcome = await readWithTimeout();

        if (outcome.type === 'idle_timeout') {
          if (!abortController.signal.aborted) {
            cleanup();
            const recovery = await recoverFromStatus(sessionId, 'stream_idle_timeout');
            if (!recovery.recovered) {
              actions.setError('连接波动，90 秒内未能自动恢复，请重试。');
            }
          }
          break;
        }

        if (outcome.type === 'read_error') {
          if (abortController.signal.aborted) {
            break;
          }
          throw outcome.error;
        }

        const { value, done } = outcome.result;
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
        if (sawOrchestratorEnd || isTerminalStatus(sessionStatus)) {
          actions.stopGeneration();
        } else if (String(sessionStatus || '').toLowerCase() === 'running') {
          const recovery = await recoverFromStatus(sessionId, 'stream_ended_while_running');
          if (!recovery.recovered) {
            actions.setError('连接已结束，但状态未完成，90 秒恢复窗口已超时。');
          }
        }
      }

    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('Stream aborted by user');
      } else {
        console.error('Stream error:', error);
        const recovery = await recoverFromStatus(sessionId, 'stream_exception');
        if (!recovery.recovered) {
          actions.setError(error.message || '流式连接异常，请稍后重试。');
        }
      }
    } finally {
      abortControllerRef.current = null;
    }
  }, [actions, cleanup, createSessionId, hydrateFromStatus, recoverFromStatus]);
  
  /**
   * 停止流式生成
   */
  const stopStream = useCallback(() => {
    cleanup();
    actions.stopGeneration();
    actions.clearRecoveryState();
  }, [cleanup, actions]);
  
  return {
    startStream,
    stopStream,
  };
}
