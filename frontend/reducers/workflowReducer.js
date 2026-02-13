// frontend/reducers/workflowReducer.js
/**
 * WeaveAI 2.0 工作流状态 Reducer
 * 处理所有工作流相关的状态更新
 */

// Action 类型常量
export const ActionTypes = {
  // 会话生命周期
  SET_SESSION: 'SET_SESSION',
  RESET_SESSION: 'RESET_SESSION',
  
  // 用户画像
  SET_PROFILE: 'SET_PROFILE',
  
  // 工作流控制
  START_GENERATION: 'START_GENERATION',
  STOP_GENERATION: 'STOP_GENERATION',
  SET_PHASE: 'SET_PHASE',
  SET_ERROR: 'SET_ERROR',
  CLEAR_ERROR: 'CLEAR_ERROR',
  
  // Agent 事件
  AGENT_START: 'AGENT_START',
  AGENT_THINKING: 'AGENT_THINKING',
  AGENT_CHUNK: 'AGENT_CHUNK',
  AGENT_END: 'AGENT_END',
  AGENT_ERROR: 'AGENT_ERROR',
  TOOL_START: 'TOOL_START',
  TOOL_END: 'TOOL_END',
  RETRY: 'RETRY',
  
  // 辩论事件
  DEBATE_ROUND_START: 'DEBATE_ROUND_START',
  AGENT_CHALLENGE: 'AGENT_CHALLENGE',
  AGENT_RESPOND: 'AGENT_RESPOND',
  CONSENSUS_REACHED: 'CONSENSUS_REACHED',
  
  // 最终报告
  SET_SYNTHESIZED_REPORT: 'SET_SYNTHESIZED_REPORT',
  
  // UI 状态
  TOGGLE_WEBSEARCH: 'TOGGLE_WEBSEARCH',

  // 断连恢复
  HYDRATE_FROM_STATUS: 'HYDRATE_FROM_STATUS',
};

/**
 * 初始状态
 * @type {import('../types/workflow').WorkflowState}
 */
export const initialState = {
  sessionId: null,
  userProfile: null,
  phase: 'init',
  isGenerating: false,
  agentResults: {},
  debateExchanges: [],
  debateRounds: 2,
  currentDebateRound: 0,
  synthesizedReport: '',
  error: null,
  enableWebsearch: false,
  toolEvents: [],
  retryEvents: [],
};

/**
 * 工作流 Reducer
 * @param {import('../types/workflow').WorkflowState} state 
 * @param {Object} action 
 * @returns {import('../types/workflow').WorkflowState}
 */
export function workflowReducer(state, action) {
  switch (action.type) {
    // ============================================
    // 会话生命周期
    // ============================================
    case ActionTypes.SET_SESSION:
      return {
        ...state,
        sessionId: action.payload.sessionId,
      };
    
    case ActionTypes.RESET_SESSION:
      return {
        ...initialState,
      };
    
    // ============================================
    // 用户画像
    // ============================================
    case ActionTypes.SET_PROFILE:
      return {
        ...state,
        userProfile: action.payload,
        // 设置画像时重置相关状态
        synthesizedReport: '',
        error: null,
        agentResults: {},
        debateExchanges: [],
        currentDebateRound: 0,
        phase: 'init',
        isGenerating: false,
      };
    
    // ============================================
    // 工作流控制
    // ============================================
    case ActionTypes.START_GENERATION:
      return {
        ...state,
        isGenerating: true,
        error: null,
        synthesizedReport: '',
        agentResults: {},
        debateExchanges: [],
        currentDebateRound: 0,
        phase: 'init',
      };
    
    case ActionTypes.STOP_GENERATION:
      return {
        ...state,
        isGenerating: false,
      };
    
    case ActionTypes.SET_PHASE:
      return {
        ...state,
        phase: action.payload,
      };
    
    case ActionTypes.SET_ERROR:
      return {
        ...state,
        error: action.payload,
        isGenerating: false,
        phase: 'error',
      };
    
    case ActionTypes.CLEAR_ERROR:
      return {
        ...state,
        error: null,
      };
    
    // ============================================
    // Agent 事件
    // ============================================
    case ActionTypes.AGENT_START:
      return {
        ...state,
        phase: 'gather',
        agentResults: {
          ...state.agentResults,
          [action.payload.agent]: {
            agentName: action.payload.agent,
            content: '',
            thinking: '',
            sources: [],
            confidence: 1.0,
            durationMs: 0,
            status: 'running',
            error: null,
          },
        },
      };
    
    case ActionTypes.AGENT_THINKING:
      return {
        ...state,
        agentResults: {
          ...state.agentResults,
          [action.payload.agent]: {
            ...state.agentResults[action.payload.agent],
            thinking: (state.agentResults[action.payload.agent]?.thinking || '') + (action.payload.content || ''),
          },
        },
      };
    
    case ActionTypes.AGENT_CHUNK:
      return {
        ...state,
        agentResults: {
          ...state.agentResults,
          [action.payload.agent]: {
            ...state.agentResults[action.payload.agent],
            content: (state.agentResults[action.payload.agent]?.content || '') + (action.payload.content || ''),
          },
        },
      };
    
    case ActionTypes.AGENT_END:
      return {
        ...state,
        agentResults: {
          ...state.agentResults,
          [action.payload.agent]: {
            ...state.agentResults[action.payload.agent],
            status: 'completed',
            durationMs: action.payload.durationMs || 0,
          },
        },
      };
    
    case ActionTypes.AGENT_ERROR:
      return {
        ...state,
        agentResults: {
          ...state.agentResults,
          [action.payload.agent]: {
            ...state.agentResults[action.payload.agent],
            status: 'failed',
            error: action.payload.error,
          },
        },
      };

    case ActionTypes.TOOL_START:
      return {
        ...state,
        toolEvents: [...state.toolEvents, { ...action.payload, status: 'start' }].slice(-100),
      };

    case ActionTypes.TOOL_END:
      return {
        ...state,
        toolEvents: [...state.toolEvents, { ...action.payload, status: 'end' }].slice(-100),
      };

    case ActionTypes.RETRY:
      return {
        ...state,
        retryEvents: [...state.retryEvents, action.payload].slice(-100),
      };
    
    // ============================================
    // 辩论事件
    // ============================================
    case ActionTypes.DEBATE_ROUND_START:
      return {
        ...state,
        phase: 'debate',
        currentDebateRound: action.payload.roundNumber,
      };
    
    case ActionTypes.AGENT_CHALLENGE:
      return {
        ...state,
        debateExchanges: [
          ...state.debateExchanges,
          {
            roundNumber: action.payload.roundNumber,
            challenger: action.payload.fromAgent,
            responder: action.payload.toAgent,
            challengeContent: action.payload.content,
            responseContent: '',
            revised: false,
          },
        ],
      };
    
    case ActionTypes.AGENT_RESPOND: {
      // 找到对应的交换记录并更新
      const exchanges = [...state.debateExchanges];
      const lastExchange = exchanges[exchanges.length - 1];
      if (lastExchange && 
          lastExchange.roundNumber === action.payload.roundNumber &&
          lastExchange.responder === action.payload.fromAgent) {
        exchanges[exchanges.length - 1] = {
          ...lastExchange,
          responseContent: action.payload.content,
          revised: action.payload.revised || false,
        };
      }
      return {
        ...state,
        debateExchanges: exchanges,
      };
    }
    
    case ActionTypes.CONSENSUS_REACHED:
      return {
        ...state,
        phase: 'synthesize',
      };
    
    // ============================================
    // 最终报告
    // ============================================
    case ActionTypes.SET_SYNTHESIZED_REPORT:
      return {
        ...state,
        synthesizedReport: action.payload,
        phase: 'complete',
        isGenerating: false,
      };
    
    case ActionTypes.TOGGLE_WEBSEARCH:
      return {
        ...state,
        enableWebsearch: !state.enableWebsearch,
      };

    case ActionTypes.HYDRATE_FROM_STATUS: {
      const payload = action.payload || {};
      const session = payload.session || {};
      const rows = Array.isArray(payload.agent_results) ? payload.agent_results : [];
      const dbDebates = Array.isArray(payload.debate_exchanges) ? payload.debate_exchanges : [];

      const agentResults = rows.reduce((acc, row) => {
        const key = row.agent_name;
        if (!key) return acc;
        acc[key] = {
          agentName: key,
          content: row.content || '',
          thinking: row.thinking || '',
          sources: Array.isArray(row.sources) ? row.sources : [],
          confidence: typeof row.confidence === 'number' ? row.confidence : 1.0,
          durationMs: row.duration_ms || 0,
          status: row.status || 'pending',
          error: row.error_message || null,
        };
        return acc;
      }, {});

      const debateExchanges = dbDebates.map((d) => ({
        roundNumber: d.round_number,
        challenger: d.challenger,
        responder: d.responder,
        challengeContent: d.challenge_content || '',
        responseContent: d.response_content || '',
        revised: !!d.revised,
      }));

      return {
        ...state,
        sessionId: session.id || state.sessionId,
        userProfile: session.profile || state.userProfile,
        phase: session.phase || state.phase,
        isGenerating: session.status === 'running',
        synthesizedReport: session.synthesized_report || state.synthesizedReport,
        error: session.error_message || state.error,
        currentDebateRound: session.current_debate_round || state.currentDebateRound,
        enableWebsearch:
          typeof session.enable_websearch === 'boolean'
            ? session.enable_websearch
            : state.enableWebsearch,
        agentResults: Object.keys(agentResults).length > 0 ? agentResults : state.agentResults,
        debateExchanges: debateExchanges.length > 0 ? debateExchanges : state.debateExchanges,
      };
    }
    
    default:
      console.warn(`Unknown action type: ${action.type}`);
      return state;
  }
}

// ============================================
// Action Creators
// ============================================

export const actions = {
  setSession: (sessionId) => ({ type: ActionTypes.SET_SESSION, payload: { sessionId } }),
  resetSession: () => ({ type: ActionTypes.RESET_SESSION }),
  setProfile: (profile) => ({ type: ActionTypes.SET_PROFILE, payload: profile }),
  startGeneration: () => ({ type: ActionTypes.START_GENERATION }),
  stopGeneration: () => ({ type: ActionTypes.STOP_GENERATION }),
  setPhase: (phase) => ({ type: ActionTypes.SET_PHASE, payload: phase }),
  setError: (error) => ({ type: ActionTypes.SET_ERROR, payload: error }),
  clearError: () => ({ type: ActionTypes.CLEAR_ERROR }),
  toggleWebsearch: () => ({ type: ActionTypes.TOGGLE_WEBSEARCH }),
  setSynthesizedReport: (report) => ({ type: ActionTypes.SET_SYNTHESIZED_REPORT, payload: report }),
  
  // Agent 事件 (用于 SSE 事件处理)
  agentStart: (agent) => ({ type: ActionTypes.AGENT_START, payload: { agent } }),
  agentThinking: (agent, content) => ({ type: ActionTypes.AGENT_THINKING, payload: { agent, content } }),
  agentChunk: (agent, content) => ({ type: ActionTypes.AGENT_CHUNK, payload: { agent, content } }),
  agentEnd: (agent, durationMs) => ({ type: ActionTypes.AGENT_END, payload: { agent, durationMs } }),
  agentError: (agent, error) => ({ type: ActionTypes.AGENT_ERROR, payload: { agent, error } }),
  toolStart: (tool, agent, metadata) => ({ type: ActionTypes.TOOL_START, payload: { tool, agent, metadata } }),
  toolEnd: (tool, agent, metadata) => ({ type: ActionTypes.TOOL_END, payload: { tool, agent, metadata } }),
  retry: (payload) => ({ type: ActionTypes.RETRY, payload }),
  
  // 辩论事件
  debateRoundStart: (roundNumber) => ({ type: ActionTypes.DEBATE_ROUND_START, payload: { roundNumber } }),
  agentChallenge: (roundNumber, fromAgent, toAgent, content) => ({
    type: ActionTypes.AGENT_CHALLENGE,
    payload: { roundNumber, fromAgent, toAgent, content },
  }),
  agentRespond: (roundNumber, fromAgent, toAgent, content, revised) => ({
    type: ActionTypes.AGENT_RESPOND,
    payload: { roundNumber, fromAgent, toAgent, content, revised },
  }),
  consensusReached: () => ({ type: ActionTypes.CONSENSUS_REACHED }),
  hydrateFromStatus: (payload) => ({ type: ActionTypes.HYDRATE_FROM_STATUS, payload }),
};
