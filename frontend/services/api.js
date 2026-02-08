import { API_ENDPOINTS } from '../lib/constants';

const handleResponse = async (response) => {
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const errorData = await response.json();
      if (errorData?.detail) detail = errorData.detail;
    } catch {
      // ignore json parse error
    }
    throw new Error(detail);
  }
  return response;
};

export const api = {
  // AI Reports (Streaming)
  marketInsight: (profile, signal) => {
    return fetch(API_ENDPOINTS.MARKET_INSIGHT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
      signal,
    }).then(handleResponse);
  },

  actionPlan: (data, signal) => {
    return fetch(API_ENDPOINTS.ACTION_PLAN, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      signal,
    }).then(handleResponse);
  },

  reviewSummary: (data, signal) => {
    return fetch(API_ENDPOINTS.REVIEW_SUMMARY, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      signal,
    }).then(handleResponse);
  },

  // Final Reports
  generateReport: (data) => {
    return fetch(API_ENDPOINTS.GENERATE_REPORT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }).then(async (res) => (await handleResponse(res)).json());
  },

  exportPdf: (reportUrl) => {
    return fetch(API_ENDPOINTS.EXPORT_PDF, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_url: reportUrl }),
    }).then(async (res) => (await handleResponse(res)).json());
  },

  // Data Analysis (FormData)
  forecastSales: (formData) => {
    return fetch(API_ENDPOINTS.FORECAST_SALES, {
      method: 'POST',
      body: formData,
    }).then(async (res) => (await handleResponse(res)).json());
  },

  productClustering: (formData) => {
    return fetch(API_ENDPOINTS.PRODUCT_CLUSTERING, {
      method: 'POST',
      body: formData,
    }).then(async (res) => (await handleResponse(res)).json());
  },

  anomalyDetection: (formData) => {
    return fetch(API_ENDPOINTS.ANOMALY_DETECTION, {
      method: 'POST',
      body: formData,
    }).then(async (res) => (await handleResponse(res)).json());
  },

  sentimentAnalysis: (formData) => {
    return fetch(API_ENDPOINTS.SENTIMENT_ANALYSIS, {
      method: 'POST',
      body: formData,
    }).then(async (res) => (await handleResponse(res)).json());
  },
};
