// frontend/types/workflow.js
/**
 * WeaveAI 2.0 类型定义
 * v2 工作流状态类型
 */

/**
 * 工作流阶段
 * @typedef {'init' | 'gather' | 'debate' | 'synthesize' | 'complete' | 'error'} WorkflowPhase
 */

/**
 * Agent 状态
 * @typedef {'pending' | 'running' | 'completed' | 'degraded' | 'skipped' | 'failed'} AgentStatus
 */

/**
 * SSE 事件类型
 * @typedef {'orchestrator_start' | 'orchestrator_end' | 'agent_start' | 'agent_thinking' | 'agent_chunk' | 'agent_end' | 'agent_error' | 'tool_start' | 'tool_end' | 'retry' | 'debate_round_start' | 'debate_round_end' | 'agent_challenge' | 'agent_challenge_end' | 'agent_respond' | 'agent_respond_end' | 'agent_followup' | 'agent_followup_end' | 'adaptive_concurrency' | 'consensus_reached' | 'error'} SSEEventType
 */

/**
 * Agent 结果
 * @typedef {Object} AgentResult
 * @property {string} agentName - Agent 名称
 * @property {string} content - 输出内容
 * @property {string} [thinking] - 思考过程
 * @property {string[]} sources - 来源列表
 * @property {number} confidence - 置信度
 * @property {number} durationMs - 耗时(毫秒)
 * @property {AgentStatus} status - 状态
 * @property {string} [error] - 错误信息
 */

/**
 * 辩论交换
 * @typedef {Object} DebateExchange
 * @property {number} roundNumber - 轮次
 * @property {string} challenger - 质疑方
 * @property {string} responder - 回应方
 * @property {string} challengeContent - 质疑内容
 * @property {string} responseContent - 回应内容
 * @property {string} [followupContent] - 追问/确认内容
 * @property {boolean} revised - 是否修正
 */

/**
 * 用户画像
 * @typedef {Object} UserProfile
 * @property {string} target_market - 目标市场
 * @property {string} supply_chain - 核心品类/供应链
 * @property {string} seller_type - 卖家类型
 * @property {number} min_price - 最低售价
 * @property {number} max_price - 最高售价
 */

/**
 * 工作流状态
 * @typedef {Object} WorkflowState
 * @property {string | null} sessionId - 会话 ID
 * @property {UserProfile | null} userProfile - 用户画像
 * @property {WorkflowPhase} phase - 当前阶段
 * @property {boolean} isGenerating - 是否正在生成
 * @property {Object<string, AgentResult>} agentResults - Agent 结果 (按名称索引)
 * @property {DebateExchange[]} debateExchanges - 辩论记录
 * @property {number} debateRounds - 配置的辩论轮数
 * @property {number} currentDebateRound - 当前辩论轮次
 * @property {string} synthesizedReport - 最终报告
 * @property {string} reportHtmlUrl - HTML 报告地址
 * @property {string | null} error - 错误信息
 * @property {boolean} enableWebsearch - 是否启用 WebSearch
 * @property {Object[]} toolEvents - 工具调用事件
 * @property {Object[]} retryEvents - 重试事件
 */

// Worker Agent 名称常量
export const WORKER_AGENTS = [
  'trend_scout',
  'competitor_analyst',
  'regulation_checker',
  'social_sentinel',
];

// Agent 中文名映射
export const AGENT_DISPLAY_NAMES = {
  trend_scout: '趋势侦察员',
  competitor_analyst: '竞争分析师',
  regulation_checker: '法规检查员',
  social_sentinel: '社媒哨兵',
  debate_challenger: '裁判Agent',
  synthesizer: '综合分析师',
};

// 工作流阶段中文名
export const PHASE_DISPLAY_NAMES = {
  init: '初始化',
  gather: '信息收集',
  debate: '多轮辩论',
  synthesize: '综合报告',
  complete: '完成',
  error: '错误',
};
