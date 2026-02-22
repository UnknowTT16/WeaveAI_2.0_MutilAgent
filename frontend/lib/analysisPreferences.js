import { DEFAULT_DEMO_PRESET_ID, DEMO_PRESETS, getDemoPresetById } from './demoPresets';

export const ANALYSIS_PREFS_STORAGE_KEY = 'weaveai_analysis_preferences_v1';

const VALID_DEGRADE_MODES = new Set(['partial', 'skip', 'fail']);
const VALID_HISTORY_FILTERS = new Set(['all', 'running', 'completed', 'failed', 'cancelled']);
const VALID_PROGRESS_VIEW_MODES = new Set(['simple', 'professional']);
const PRESET_IDS = new Set(DEMO_PRESETS.map((preset) => preset.id));

const DEFAULT_ANALYSIS_PREFS = {
  defaultDemoPresetId: DEFAULT_DEMO_PRESET_ID,
  defaultDebateRounds: getDemoPresetById(DEFAULT_DEMO_PRESET_ID).request.debateRounds,
  retryMaxAttempts: 2,
  retryBackoffMs: 300,
  degradeMode: 'partial',
  historyStatusFilter: 'all',
  progressViewMode: 'simple',
};

function clampInt(value, min, max, fallback) {
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

export function getDefaultAnalysisPreferences() {
  return { ...DEFAULT_ANALYSIS_PREFS };
}

export function sanitizeAnalysisPreferences(raw) {
  const prefs = raw && typeof raw === 'object' ? raw : {};

  const presetId = PRESET_IDS.has(String(prefs.defaultDemoPresetId))
    ? String(prefs.defaultDemoPresetId)
    : DEFAULT_ANALYSIS_PREFS.defaultDemoPresetId;

  const presetRounds = getDemoPresetById(presetId).request.debateRounds;

  const defaultDebateRounds = clampInt(
    prefs.defaultDebateRounds,
    0,
    2,
    presetRounds
  );

  const retryMaxAttempts = clampInt(
    prefs.retryMaxAttempts,
    1,
    4,
    DEFAULT_ANALYSIS_PREFS.retryMaxAttempts
  );

  const retryBackoffMs = clampInt(
    prefs.retryBackoffMs,
    100,
    2000,
    DEFAULT_ANALYSIS_PREFS.retryBackoffMs
  );

  const degradeMode = VALID_DEGRADE_MODES.has(String(prefs.degradeMode))
    ? String(prefs.degradeMode)
    : DEFAULT_ANALYSIS_PREFS.degradeMode;

  const historyStatusFilter = VALID_HISTORY_FILTERS.has(String(prefs.historyStatusFilter))
    ? String(prefs.historyStatusFilter)
    : DEFAULT_ANALYSIS_PREFS.historyStatusFilter;

  const progressViewMode = VALID_PROGRESS_VIEW_MODES.has(String(prefs.progressViewMode))
    ? String(prefs.progressViewMode)
    : DEFAULT_ANALYSIS_PREFS.progressViewMode;

  return {
    defaultDemoPresetId: presetId,
    defaultDebateRounds,
    retryMaxAttempts,
    retryBackoffMs,
    degradeMode,
    historyStatusFilter,
    progressViewMode,
  };
}

export function loadAnalysisPreferences() {
  if (typeof window === 'undefined') {
    return getDefaultAnalysisPreferences();
  }

  try {
    const raw = window.localStorage.getItem(ANALYSIS_PREFS_STORAGE_KEY);
    if (!raw) return getDefaultAnalysisPreferences();
    return sanitizeAnalysisPreferences(JSON.parse(raw));
  } catch {
    return getDefaultAnalysisPreferences();
  }
}

export function saveAnalysisPreferences(prefs) {
  if (typeof window === 'undefined') return;

  try {
    const normalized = sanitizeAnalysisPreferences(prefs);
    window.localStorage.setItem(
      ANALYSIS_PREFS_STORAGE_KEY,
      JSON.stringify(normalized)
    );
  } catch {
    // 忽略本地存储异常，不影响主流程
  }
}
