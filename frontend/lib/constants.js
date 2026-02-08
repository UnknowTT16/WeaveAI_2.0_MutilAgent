export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export const STREAM_MARKERS = {
  THINK_END: '<<<<THINKING_ENDS>>>>',
  REPORT_START: '<<<<REPORT_STARTS>>>>',
  FUNCTION_CALL_REGEX: /<\|FunctionCallBegin\|>[\s\S]*?<\|FunctionCallEnd\|>/g,
};

export const API_ENDPOINTS = {
  MARKET_INSIGHT: `${API_BASE_URL}/api/v1/reports/market-insight`,
  ACTION_PLAN: `${API_BASE_URL}/api/v1/reports/action-plan`,
  REVIEW_SUMMARY: `${API_BASE_URL}/api/v1/reports/review-summary`,
  GENERATE_REPORT: `${API_BASE_URL}/api/v1/reports/generate-and-save-report`,
  EXPORT_PDF: `${API_BASE_URL}/api/v1/reports/export-pdf`,
  FORECAST_SALES: `${API_BASE_URL}/api/v1/data/forecast-sales`,
  PRODUCT_CLUSTERING: `${API_BASE_URL}/api/v1/data/product-clustering`,
  ANOMALY_DETECTION: `${API_BASE_URL}/api/v1/data/anomaly-detection`,
  SENTIMENT_ANALYSIS: `${API_BASE_URL}/api/v1/data/sentiment-analysis`,
};
