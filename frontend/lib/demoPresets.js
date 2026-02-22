// frontend/lib/demoPresets.js

export const DEMO_PRESETS = [
  {
    id: 'fast60',
    label: '60 秒极速',
    targetDuration: '约 60 秒',
    description: '跳过辩论，强调稳定与速度，适合开场快速价值展示。',
    request: {
      debateRounds: 0,
      enableWebsearch: false,
      enableFollowup: false,
      retryMaxAttempts: 1,
      retryBackoffMs: 100,
      degradeMode: 'partial',
    },
  },
  {
    id: 'standard3m',
    label: '3 分钟标准',
    targetDuration: '约 3 分钟',
    description: '开启 1 轮同行评审，展示多 Agent 协作与结构化结论。',
    request: {
      debateRounds: 1,
      enableWebsearch: false,
      enableFollowup: true,
      retryMaxAttempts: 2,
      retryBackoffMs: 300,
      degradeMode: 'partial',
    },
  },
  {
    id: 'deep',
    label: '深度演示',
    targetDuration: '3 分钟以上',
    description: '完整辩论与红队审查，适合答辩环节展示深度。',
    request: {
      debateRounds: 2,
      enableWebsearch: true,
      enableFollowup: true,
      retryMaxAttempts: 2,
      retryBackoffMs: 300,
      degradeMode: 'partial',
    },
  },
];

export const DEFAULT_DEMO_PRESET_ID = 'standard3m';

export function getDemoPresetById(presetId) {
  return DEMO_PRESETS.find((preset) => preset.id === presetId) || DEMO_PRESETS[0];
}
