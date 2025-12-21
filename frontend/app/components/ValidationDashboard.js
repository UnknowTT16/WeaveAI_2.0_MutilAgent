// frontend/app/components/ValidationDashboard.js
'use client';

import { useState, useEffect, useMemo } from 'react';
import dynamic from 'next/dynamic';
import FileUpload from './FileUpload';
import DataTable from './DataTable';
import SentimentAnalysis from './SentimentAnalysis';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

export default function ValidationDashboard({
  onValidationUpdate,
  analysisResults = {},
  sentimentAiReport
}) {
  const [salesFile, setSalesFile] = useState(null);
  const [reviewsFile, setReviewsFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('forecast');

  const [selectedCluster, setSelectedCluster] = useState(null);
  const [selectedAnomalySku, setSelectedAnomalySku] = useState(null);

  const [isSentimentGenerating, setIsSentimentGenerating] = useState(false);
  const [sentimentError, setSentimentError] = useState('');

  useEffect(() => {
    const clustering = analysisResults['product-clustering'];
    if (!clustering) {
      setSelectedCluster(null);
      return;
    }
    const summary = clustering.clustering_results.cluster_summary;
    if (selectedCluster === null && summary?.length) {
      const hotCluster = summary.find((c) => c.is_hot_cluster) ?? summary[0];
      setSelectedCluster(hotCluster?.cluster ?? null);
    }
  }, [analysisResults, selectedCluster]);

  useEffect(() => {
    const anomaly = analysisResults['anomaly-detection'];
    if (!anomaly || !anomaly.sku_summary?.length) {
      setSelectedAnomalySku(null);
      return;
    }
    if (!selectedAnomalySku) {
      setSelectedAnomalySku(anomaly.sku_summary[0].sku);
    } else if (!anomaly.sku_summary.some((row) => row.sku === selectedAnomalySku)) {
      setSelectedAnomalySku(anomaly.sku_summary[0].sku);
    }
  }, [analysisResults, selectedAnomalySku]);

  const displayedProducts = useMemo(() => {
    const clustering = analysisResults['product-clustering'];
    if (!clustering || selectedCluster === null) {
      return [];
    }
    const points = clustering.clustering_results.product_points;
    return points
      .filter((p) => p.cluster === selectedCluster)
      .sort((a, b) => b.total_amount - a.total_amount);
  }, [analysisResults, selectedCluster]);

  const handleAnalysis = async (analysisType, file, endpoint) => {
    if (!file) {
      setError(`请先上传 ${analysisType === 'reviews' ? '评论' : '销售'} 数据文件。`);
      return;
    }
    setIsLoading(true);
    setError('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/api/v1/data/${endpoint}`, {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || '分析失败，请检查文件格式。');
      }
      const result = await response.json();
      onValidationUpdate({
        results: { ...analysisResults, [endpoint]: result }
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  };

  const renderAnomalyTab = () => {
    const anomaly = analysisResults['anomaly-detection'];
    if (!anomaly) {
      return (
        <button
          onClick={() => handleAnalysis('sales', salesFile, 'anomaly-detection')}
          disabled={isLoading || !salesFile}
          className="btn-primary disabled:opacity-50"
        >
          运行异常监测
        </button>
      );
    }

    const timeseries = anomaly.timeseries || [];
    const skuSummary = anomaly.sku_summary || [];
    const topFlags = anomaly.top_flags || [];
    const activeSku = selectedAnomalySku || (skuSummary[0]?.sku ?? null);
    const seriesForSku = activeSku ? timeseries.filter((row) => row.sku === activeSku) : timeseries;
    const anomalyPoints = seriesForSku.filter((row) => row.is_anomaly);

    return (
      <div className="space-y-10">
        <div>
          <h3 className="text-xl font-semibold text-white mb-4">销量异常趋势</h3>
          {seriesForSku.length === 0 ? (
            <p className="text-gray-400 text-sm">暂无可视化数据，请先选择一个 SKU。</p>
          ) : (
            <Plot
              data={[
                {
                  x: seriesForSku.map((p) => p.date),
                  y: seriesForSku.map((p) => p.total_qty),
                  type: 'scatter',
                  mode: 'lines',
                  name: '实际销量',
                  line: { color: '#60a5fa' },
                },
                {
                  x: seriesForSku.map((p) => p.date),
                  y: seriesForSku.map((p) => p.expected_qty),
                  type: 'scatter',
                  mode: 'lines',
                  name: '期望销量',
                  line: { color: '#fbbf24', dash: 'dash' },
                },
                {
                  x: anomalyPoints.map((p) => p.date),
                  y: anomalyPoints.map((p) => p.total_qty),
                  type: 'scatter',
                  mode: 'markers',
                  name: '异常点',
                  marker: { color: '#f87171', size: 9, symbol: 'x' },
                },
              ]}
              layout={{
                template: 'plotly_dark',
                height: 400,
                margin: { t: 30, l: 50, r: 30, b: 60 },
                xaxis: { title: '日期' },
                yaxis: { title: '销量' },
              }}
              useResizeHandler
              style={{ width: '100%', height: '100%' }}
            />
          )}
        </div>

        <DataTable
          title="SKU 异常概览 (点击行以切换曲线)"
          data={skuSummary}
          onRowClick={(row) => setSelectedAnomalySku(row.sku)}
          selectedRowIdentifier={activeSku}
        />

        {topFlags.length > 0 && (
          <DataTable
            title="最近异常明细"
            data={topFlags.map((flag) => ({
              ...flag,
              date: flag.date,
            }))}
          />
        )}
      </div>
    );
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'forecast': {
        const forecast = analysisResults['forecast-sales'];
        if (forecast) {
          const figData = JSON.parse(forecast);
          return (
            <Plot
              data={figData.data}
              layout={figData.layout}
              useResizeHandler
              style={{ width: '100%', height: '100%' }}
            />
          );
        }
        return (
          <button
            onClick={() => handleAnalysis('sales', salesFile, 'forecast-sales')}
            disabled={isLoading || !salesFile}
            className="btn-primary disabled:opacity-50"
          >
            开始销售预测
          </button>
        );
      }

      case 'clustering': {
        const clustering = analysisResults['product-clustering'];
        if (!clustering) {
          return (
            <button
              onClick={() => handleAnalysis('sales', salesFile, 'product-clustering')}
              disabled={isLoading || !salesFile}
              className="btn-primary disabled:opacity-50"
            >
              开始深度数据挖掘
            </button>
          );
        }

        const { clustering_results, basket_analysis_results } = clustering;
        const { elbow_data, product_points, cluster_summary } = clustering_results;

        return (
          <div className="space-y-12">
            <div>
              <h3 className="text-xl font-semibold text-white mb-4">K-Means 聚类分析</h3>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Plot
                  data={[{
                    x: elbow_data.map((d) => d.k),
                    y: elbow_data.map((d) => d.wcss),
                    type: 'scatter',
                    mode: 'lines+markers',
                    marker: { color: '#818cf8' },
                  }]}
                  layout={{
                    title: 'WCSS vs. 聚类数量 (K)',
                    xaxis: { title: '聚类数量 K' },
                    yaxis: { title: '簇内平方和 (WCSS)' },
                    template: 'plotly_dark',
                  }}
                  useResizeHandler
                  style={{ width: '100%', height: '400px' }}
                />
                <Plot
                  data={[{
                    x: product_points.map((p) => p.total_amount),
                    y: product_points.map((p) => p.total_qty),
                    z: product_points.map((p) => p.order_count),
                    text: product_points.map((p) => p.SKU),
                    hoverinfo: 'x+y+z+text',
                    type: 'scatter3d',
                    mode: 'markers',
                    marker: {
                      size: 5,
                      color: product_points.map((p) => p.cluster),
                      colorscale: 'Viridis',
                      opacity: 0.85,
                    },
                  }]}
                  layout={{
                    title: '产品分布 3D 视图',
                    template: 'plotly_dark',
                    scene: {
                      xaxis: { title: '总销售额' },
                      yaxis: { title: '总销量' },
                      zaxis: { title: '订单数' },
                    },
                  }}
                  useResizeHandler
                  style={{ width: '100%', height: '500px' }}
                />
              </div>
            </div>

            <div className="mb-8">
              <DataTable
                title="各商品簇特征均值 (点击下方行以查看详情)"
                data={cluster_summary}
                onRowClick={(row) => setSelectedCluster(row.cluster)}
                selectedRowIdentifier={selectedCluster}
              />
            </div>

            {displayedProducts.length > 0 && (
              <DataTable
                title={`簇 ${selectedCluster?.toFixed ? selectedCluster.toFixed(0) : selectedCluster} 内的商品列表 (${displayedProducts.length} 条)`}
                data={displayedProducts}
              />
            )}

            <div className="border-t border-gray-700" />

            <div>
              <h3 className="text-xl font-semibold text-white mb-4">购物篮分析 (关联规则)</h3>
              {basket_analysis_results.length > 0 ? (
                <>
                  <p className="text-sm text-gray-400 mb-4">
                    提升度 (lift) &gt; 1 表示强关联，是捆绑销售或交叉营销的好机会。
                  </p>
                  <DataTable title="热门商品组合推荐" data={basket_analysis_results} />
                </>
              ) : (
                <p className="text-gray-400">当前数据未发现显著的商品关联规则。</p>
              )}
            </div>
          </div>
        );
      }

      case 'anomaly':
        return renderAnomalyTab();

      case 'sentiment': {
        const sentimentResult = analysisResults['sentiment-analysis'];
        if (sentimentResult) {
          return (
            <SentimentAnalysis
              analysisResult={sentimentResult}
              aiReport={sentimentAiReport}
              setAiReport={(report) => onValidationUpdate({ sentimentReport: report })}
              isGenerating={isSentimentGenerating}
              setIsGenerating={setIsSentimentGenerating}
              error={sentimentError}
              setError={setSentimentError}
            />
          );
        }
        return (
          <button
            onClick={() => handleAnalysis('reviews', reviewsFile, 'sentiment-analysis')}
            disabled={isLoading || !reviewsFile}
            className="btn-primary disabled:opacity-50"
          >
            开始情感分析
          </button>
        );
      }

      default:
        return null;
    }
  };

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h3 className="text-lg font-medium text-white mb-2">1. 上传销售报表</h3>
          <FileUpload title="Amazon 销售报表 (.csv, .parquet)" onFileSelect={setSalesFile} isLoading={isLoading} />
          {salesFile && <p className="text-sm text-gray-400 mt-2">已选择: {salesFile.name}</p>}
        </div>
        <div>
          <h3 className="text-lg font-medium text-white mb-2">2. 上传评论数据 (可选)</h3>
          <FileUpload title="Amazon 评论数据 (.csv, .parquet)" onFileSelect={setReviewsFile} isLoading={isLoading} />
          {reviewsFile && <p className="text-sm text-gray-400 mt-2">已选择: {reviewsFile.name}</p>}
        </div>
      </div>

      <div className="bg-gray-900/50 rounded-lg p-6 min-h-[300px]">
        <h3 className="text-lg font-medium text-white mb-4">分析仪表盘</h3>
        <div className="border-b border-gray-700 mb-4">
          <nav className="-mb-px flex space-x-8" aria-label="Tabs">
            <button onClick={() => setActiveTab('forecast')} className={`${activeTab === 'forecast' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}>
              销售预测
            </button>
            <button onClick={() => setActiveTab('clustering')} className={`${activeTab === 'clustering' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}>
              深度数据挖掘
            </button>
            <button onClick={() => setActiveTab('anomaly')} className={`${activeTab === 'anomaly' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}>
              异常监测
            </button>
            <button onClick={() => setActiveTab('sentiment')} className={`${activeTab === 'sentiment' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-gray-400 hover:text-gray-200 hover:border灰-500'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}>
              情感分析
            </button>
          </nav>
        </div>
        <div className="mt-4">
          {isLoading && <p className="text-indigo-400 animate-pulse">分析中，请稍候...</p>}
          {error && <p className="text-red-400">{error}</p>}
          {!isLoading && !error && renderTabContent()}
        </div>
      </div>
    </div>
  );
}
