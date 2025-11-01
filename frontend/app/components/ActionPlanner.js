// frontend/app/components/ActionPlanner.js
'use client';

import { useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import debounce from 'lodash/debounce';

export default function ActionPlanner({
  marketReport,
  validationSummary,
  sentimentReport,
  analysisResults,
}) {
  const [isLoading, setIsLoading] = useState(false);
  const [aiReport, setAiReport] = useState({ thinking: '', report: '' });
  const [error, setError] = useState('');

  const [isGeneratingFinal, setIsGeneratingFinal] = useState(false);
  const [finalReportUrl, setFinalReportUrl] = useState('');
  const [finalReportError, setFinalReportError] = useState('');

  // >>> 新增：PDF 导出相关状态
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [pdfUrl, setPdfUrl] = useState('');
  const [pdfError, setPdfError] = useState('');
  // <<< 新增

  const debouncedSetAiReport = useMemo(
    () => debounce((content) => { setAiReport(content); }, 120),
    []
  );

  const handleGeneratePlan = async () => {
    setIsLoading(true);
    setError('');
    setAiReport({ thinking: '正在整合信息并调用 AI...', report: '' });

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL}/api/v1/reports/action-plan`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            market_report: marketReport,
            validation_summary: validationSummary,
            sentiment_report: sentimentReport || '',
          }),
        }
      );

      if (!response.ok) {
        let detail = 'AI 行动计划服务请求失败。';
        try { const err = await response.json(); if (err?.detail) detail = err.detail; } catch {}
        throw new Error(detail);
      }

      if (!response.body) {
        const data = await response.json();
        setAiReport({ thinking: data.thinking || '', report: data.report || '' });
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullResponse = '';
      const thinkEndMarker = '<<<<THINKING_ENDS>>>>';
      const reportStartMarker = '<<<<REPORT_STARTS>>>>';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        fullResponse += decoder.decode(value, { stream: true });

        let currentThinking = '';
        let currentReport = '';
        if (fullResponse.includes(reportStartMarker)) {
          const parts = fullResponse.split(reportStartMarker, 2);
          currentThinking = parts[0].replace(thinkEndMarker, '');
          currentReport = parts[1];
        } else if (fullResponse.includes(thinkEndMarker)) {
          currentThinking = fullResponse.replace(thinkEndMarker, '');
        } else {
          currentThinking = fullResponse;
        }

        debouncedSetAiReport({ thinking: currentThinking, report: currentReport });
      }
      debouncedSetAiReport.flush();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsLoading(false);
    }
  };

  // 生成最终 HTML 报告
  const handleGenerateFinalReport = async () => {
    setIsGeneratingFinal(true);
    setFinalReportError('');
    setFinalReportUrl('');
    setPdfUrl(''); // 重新生成 HTML 时，清空旧的 PDF 地址

    try {
      const clusteringPack = analysisResults?.['product-clustering'] || null;
      const inner = clusteringPack?.clustering_results || null;

      const payload = {
        market_report: marketReport,
        validation_summary: validationSummary,
        action_plan: aiReport?.report || '',
        sentiment_report: sentimentReport || '',
        forecast_chart_json: analysisResults?.['forecast-sales'] || null,
        clustering_data: inner ? {
          cluster_summary: inner.cluster_summary,
          product_points: inner.product_points,
        } : null,
        elbow_chart_json: inner?.elbow_chart_json || null,
        scatter_3d_chart_json: inner?.scatter_3d_chart_json || null,
        basket_analysis_data: clusteringPack?.basket_analysis_results || null,
      };

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL}/api/v1/reports/generate-and-save-report`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }
      );

      if (!response.ok) {
        let detail = '生成最终报告失败。';
        try { const errData = await response.json(); if (errData?.detail) detail = errData.detail; } catch {}
        throw new Error(detail);
      }

      const result = await response.json();
      setFinalReportUrl(result.report_url);
    } catch (e) {
      setFinalReportError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsGeneratingFinal(false);
    }
  };

  // >>> 新增：导出 PDF
  const handleExportPdf = async () => {
    if (!finalReportUrl) return;
    setIsExportingPdf(true);
    setPdfError('');
    setPdfUrl('');

    try {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL}/api/v1/reports/export-pdf`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ report_url: finalReportUrl }),
        }
      );

      if (!resp.ok) {
        let detail = '导出 PDF 失败。';
        try { const err = await resp.json(); if (err?.detail) detail = err.detail; } catch {}
        throw new Error(detail);
      }

      const data = await resp.json();
      setPdfUrl(data.pdf_url);
    } catch (e) {
      setPdfError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsExportingPdf(false);
    }
  };
  // <<< 新增

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
      <div className="rounded-2xl border border-slate-700 bg-slate-800 p-6 shadow-sm">
        <h2 className="text-2xl font-bold text-slate-100 mb-4">第三步：行动计划 (Action Plan)</h2>

        <div className="flex flex-wrap gap-3 mb-4">
          <button
            type="button"
            onClick={handleGeneratePlan}
            disabled={isLoading}
            className="px-4 py-2 rounded-xl bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-60 shadow"
          >
            {isLoading ? '生成中…' : '💡 生成我的行动计划'}
          </button>

          <button
            type="button"
            onClick={handleGenerateFinalReport}
            disabled={isGeneratingFinal || !aiReport?.report}
            className="px-4 py-2 rounded-xl bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-60 shadow"
            title={!aiReport?.report ? '请先生成行动计划' : ''}
          >
            {isGeneratingFinal ? '导出中…' : '📊 生成可视化HTML报表'}
          </button>

          {/* 新增：导出 PDF 按钮（需要已有 HTML 报告 URL） */}
          <button
            type="button"
            onClick={handleExportPdf}
            disabled={!finalReportUrl || isExportingPdf}
            className="px-4 py-2 rounded-xl bg-sky-600 text-white hover:bg-sky-500 disabled:opacity-60 shadow"
            title={!finalReportUrl ? '请先生成HTML报表' : ''}
          >
            {isExportingPdf ? '正在导出…' : '🖨️ 导出为 PDF'}
          </button>
        </div>

        {!!error && (
          <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-red-700 mb-5">
            {error}
          </div>
        )}

        <div className="rounded-xl border border-slate-700 bg-slate-800 p-4 mb-4">
          <div className="text-sm font-medium text-slate-200 mb-2">思考过程</div>
          <div className="text-slate-100 whitespace-pre-wrap min-h-[88px]">
            {aiReport.thinking || (isLoading ? '正在整合信息并调用 AI...' : '')}
          </div>
        </div>

        <div className="rounded-xl border border-slate-700 bg-slate-800 p-4">
          <div className="text-sm font-medium text-slate-200 mb-2">行动计划预览</div>
          <div className="prose prose-invert max-w-none">
            {aiReport.report ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{aiReport.report}</ReactMarkdown>
            ) : (
              <div className="text-slate-300">暂无内容</div>
            )}
          </div>
        </div>

        {(isGeneratingFinal || finalReportUrl || finalReportError || pdfUrl || pdfError) && (
          <div className="mt-6 rounded-xl border border-slate-700 bg-slate-800 p-4">
            <div className="font-semibold text-slate-100 mb-2">最终报告</div>

            {isGeneratingFinal && <div className="text-slate-300">正在导出与保存，请稍候…</div>}
            {!!finalReportError && <div className="text-red-400">{finalReportError}</div>}

            {!!finalReportUrl && (
              <div className="text-slate-200 mb-2">
                已生成 HTML： 
                <a href={finalReportUrl} target="_blank" rel="noopener noreferrer" className="font-semibold text-indigo-300 hover:text-indigo-200 ml-1">
                  点击查看
                </a>
              </div>
            )}

            {/* 新增：PDF 结果展示 */}
            {isExportingPdf && <div className="text-slate-300">正在导出 PDF…</div>}
            {!!pdfError && <div className="text-red-400">{pdfError}</div>}
            {!!pdfUrl && (
              <div className="text-slate-200">
                已生成 PDF：
                <a href={pdfUrl} target="_blank" rel="noopener noreferrer" className="font-semibold text-sky-300 hover:text-sky-200 ml-1">
                  点击下载 / 查看
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
