export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export const API_ENDPOINTS = {
  MARKET_INSIGHT_STREAM: `${API_BASE_URL}/api/v2/market-insight/stream`,
  MARKET_INSIGHT_STATUS: `${API_BASE_URL}/api/v2/market-insight/status`,
  MARKET_INSIGHT_SESSIONS: `${API_BASE_URL}/api/v2/market-insight/sessions`,
  MARKET_INSIGHT_HEALTH: `${API_BASE_URL}/api/v2/market-insight/health`,
  MARKET_INSIGHT_EXPORT: `${API_BASE_URL}/api/v2/market-insight/export`,
};
