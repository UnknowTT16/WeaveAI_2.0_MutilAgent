'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

function formatSpec(spec) {
  try {
    return JSON.stringify(spec || {}, null, 2);
  } catch {
    return '{}';
  }
}

function ChartCard({ chart }) {
  const mountRef = useRef(null);
  const [renderError, setRenderError] = useState('');
  const [rendered, setRendered] = useState(false);
  const rawSpecText = useMemo(() => formatSpec(chart?.spec), [chart?.spec]);

  useEffect(() => {
    let cancelled = false;
    let view = null;
    const mountEl = mountRef.current;

    async function renderChart() {
      if (!mountEl || !chart?.spec) {
        setRendered(false);
        setRenderError('图表配置缺失。');
        return;
      }

      setRendered(false);
      setRenderError('');

      try {
        const embedModule = await import('vega-embed');
        const vegaEmbed = embedModule.default || embedModule;
        mountEl.innerHTML = '';
        const result = await vegaEmbed(mountEl, chart.spec, {
          actions: false,
          renderer: 'svg',
        });
        view = result?.view || null;

        if (!cancelled) {
          setRendered(true);
        }
      } catch (error) {
        if (cancelled) return;
        setRendered(false);
        setRenderError(error?.message || '图表渲染失败');
      }
    }

    renderChart();

    return () => {
      cancelled = true;
      try {
        view?.finalize?.();
      } catch {
        // 无需阻断页面
      }
      if (mountEl) mountEl.innerHTML = '';
    };
  }, [chart]);

  return (
    <article className="surface-card p-4 md:p-5">
      <h3 className="text-sm font-semibold text-foreground">{chart?.title || '关键图表'}</h3>
      {chart?.description && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{chart.description}</p>}

      <div ref={mountRef} className="mt-3 min-h-[220px] w-full rounded-xl border border-border bg-background" />

      {!rendered && (
        <div className="mt-3 rounded-xl border border-dashed border-amber-500/40 bg-amber-500/5 p-3">
          <p className="text-xs leading-relaxed text-muted-foreground">
            {chart?.fallback_text || '图表渲染失败，已回退到文本和原始配置。'}
          </p>
          {renderError && <p className="mt-2 text-xs text-red-500">{renderError}</p>}
          <details className="mt-2">
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground">查看原始配置</summary>
            <pre className="mt-2 max-h-56 overflow-auto rounded-lg bg-slate-950 p-3 text-[11px] text-slate-100">
              {rawSpecText}
            </pre>
          </details>
        </div>
      )}
    </article>
  );
}

export default function VegaLiteCharts({ reportCharts, maxCharts = null }) {
  const allCharts = Array.isArray(reportCharts?.charts) ? reportCharts.charts : [];
  const charts = typeof maxCharts === 'number' ? allCharts.slice(0, maxCharts) : allCharts;

  if (charts.length === 0) {
    return (
      <div className="surface-card py-8 text-center text-sm text-muted-foreground">
        暂无图表数据，完成分析后会自动生成。
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">图表用于辅助理解结论，仍建议结合上方关键结论一起阅读。</p>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {charts.map((chart, index) => (
          <ChartCard key={chart?.id || `chart-${index}`} chart={chart} />
        ))}
      </div>
    </div>
  );
}
