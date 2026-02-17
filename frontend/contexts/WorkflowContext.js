// frontend/contexts/WorkflowContext.js
/**
 * WeaveAI 2.0 工作流 Context
 * 提供全局状态管理
 */

'use client';

import { createContext, useContext, useReducer, useMemo } from 'react';
import { workflowReducer, initialState, actions } from '../reducers/workflowReducer';

// 创建 Context
const WorkflowContext = createContext(null);
const WorkflowDispatchContext = createContext(null);

/**
 * WorkflowProvider 组件
 * 包装应用提供全局状态
 */
export function WorkflowProvider({ children }) {
  const [state, dispatch] = useReducer(workflowReducer, initialState);
  
  // 封装常用 dispatch 方法
  const boundActions = useMemo(() => ({
    // 会话管理
    setSession: (sessionId) => dispatch(actions.setSession(sessionId)),
    resetSession: () => dispatch(actions.resetSession()),
    
    // 用户画像
    setProfile: (profile) => dispatch(actions.setProfile(profile)),
    
    // 工作流控制
    startGeneration: () => dispatch(actions.startGeneration()),
    stopGeneration: () => dispatch(actions.stopGeneration()),
    setPhase: (phase) => dispatch(actions.setPhase(phase)),
    setError: (error) => dispatch(actions.setError(error)),
    clearError: () => dispatch(actions.clearError()),
    
    // UI 状态
    toggleWebsearch: () => dispatch(actions.toggleWebsearch()),
    
    // 报告
    setSynthesizedReport: (report, reportHtmlUrl = null) =>
      dispatch(actions.setSynthesizedReport(report, reportHtmlUrl)),
    
    // SSE 事件处理器
    handleSSEEvent: (event) => {
      switch (event.event) {
        case 'orchestrator_start':
          dispatch(actions.startGeneration());
          if (event.session_id) {
            dispatch(actions.setSession(event.session_id));
          }
          break;
        case 'orchestrator_end':
          dispatch(
            actions.setSynthesizedReport(
              event.final_report || '',
              event.report_html_url || null
            )
          );
          break;
        case 'agent_start':
          dispatch(actions.agentStart(event.agent));
          break;
        case 'agent_thinking':
        case 'agent_thinking_chunk':
          dispatch(actions.agentThinking(event.agent, event.content || ''));
          break;
        case 'agent_chunk':
        case 'agent_output':
          dispatch(actions.agentChunk(event.agent, event.content || ''));
          break;
        case 'agent_end':
          dispatch(
            actions.agentEnd(
              event.agent,
              event.duration_ms,
              event.status || 'completed',
              event.error || null
            )
          );
          break;
        case 'agent_error':
          dispatch(actions.agentError(event.agent, event.error));
          break;
        case 'tool_start':
          dispatch(actions.toolStart(event.tool, event.agent, event));
          break;
        case 'tool_end':
          dispatch(actions.toolEnd(event.tool, event.agent, event));
          break;
        case 'tool_error':
          dispatch(actions.toolError(event.tool, event.agent, event));
          break;
        case 'guardrail_triggered':
          dispatch(actions.toolEnd('guardrail', event.agent || 'system', event));
          break;
        case 'retry':
          dispatch(actions.retry(event));
          break;
        case 'gather_complete':
        case 'debate_round_end':
        case 'agent_followup':
          // 当前版本无需前端状态更新，保留以避免 unknown 噪音
          break;
        case 'debate_round_start':
          dispatch(actions.debateRoundStart(event.round_number));
          break;
        case 'agent_challenge':
          // start 事件，不更新内容
          break;
        case 'agent_challenge_end':
          dispatch(actions.agentChallenge(
            event.round_number,
            event.from_agent,
            event.to_agent,
            event.challenge_content || event.content || event.content_preview || ''
          ));
          break;
        case 'agent_respond':
          // start 事件，不更新内容
          break;
        case 'agent_respond_end':
          dispatch(actions.agentRespond(
            event.round_number,
            event.from_agent,
            event.to_agent,
            event.response_content || event.content || event.content_preview || '',
            event.revised
          ));
          break;
        case 'agent_followup_end':
          dispatch(
            actions.agentFollowup(
              event.round_number,
              event.from_agent,
              event.to_agent,
              event.followup_content || event.content || ''
            )
          );
          break;
        case 'adaptive_concurrency':
          dispatch(actions.toolEnd('adaptive_concurrency', event.agent || 'system', event));
          break;
        case 'consensus_reached':
          dispatch(actions.consensusReached());
          break;
        case 'error':
          dispatch(actions.setError(event.error));
          break;
        default:
          // 保持静默，避免前端噪音
          break;
      }
    },

    hydrateFromStatus: (payload) => dispatch(actions.hydrateFromStatus(payload)),
  }), [dispatch]);
  
  return (
    <WorkflowContext.Provider value={state}>
      <WorkflowDispatchContext.Provider value={boundActions}>
        {children}
      </WorkflowDispatchContext.Provider>
    </WorkflowContext.Provider>
  );
}

/**
 * 获取工作流状态 Hook
 * @returns {import('../types/workflow').WorkflowState}
 */
export function useWorkflowState() {
  const context = useContext(WorkflowContext);
  if (context === null) {
    throw new Error('useWorkflowState must be used within a WorkflowProvider');
  }
  return context;
}

/**
 * 获取工作流 dispatch 方法 Hook
 * @returns {Object} 封装的 dispatch 方法
 */
export function useWorkflowActions() {
  const context = useContext(WorkflowDispatchContext);
  if (context === null) {
    throw new Error('useWorkflowActions must be used within a WorkflowProvider');
  }
  return context;
}

/**
 * 组合 Hook：同时获取状态和 actions
 * @returns {[import('../types/workflow').WorkflowState, Object]}
 */
export function useWorkflow() {
  return [useWorkflowState(), useWorkflowActions()];
}

/**
 * 计算派生状态的 Hook
 * 例如：stepsStatus, 是否可以进入下一步等
 */
export function useWorkflowDerived() {
  const state = useWorkflowState();
  
  return useMemo(() => {
    // 计算已完成的 Agent 数量
    const completedAgents = Object.values(state.agentResults)
      .filter(r => ['completed', 'degraded', 'skipped'].includes(r.status)).length;
    
    const totalAgents = Object.keys(state.agentResults).length;
    
    // 是否所有 Agent 都完成
    const allAgentsCompleted = totalAgents > 0 && completedAgents === totalAgents;
    
    return {
      completedAgents,
      totalAgents,
      allAgentsCompleted,
      hasReport: !!state.synthesizedReport,
    };
  }, [state.synthesizedReport, state.agentResults]);
}
