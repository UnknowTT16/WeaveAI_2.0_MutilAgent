// frontend/app/components/ValidationDashboard.js
'use client';

import { useState, useCallback, useEffect, useMemo } from 'react';
import dynamic from 'next/dynamic';
import FileUpload from './FileUpload';
import DataTable from './DataTable';
import SentimentAnalysis from './SentimentAnalysis';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

export default function ValidationDashboard({ 
  onValidationUpdate,
  analysisResults,
  sentimentAiReport
}) {
  // --- Local State for UI Management ---
  const [salesFile, setSalesFile] = useState(null);
  const [reviewsFile, setReviewsFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('forecast');
  
  // Clustering UI State
  const [selectedCluster, setSelectedCluster] = useState(null);

  // Sentiment Analysis UI State
  const [isSentimentGenerating, setIsSentimentGenerating] = useState(false);
  const [sentimentError, setSentimentError] = useState('');

  // --- Effects ---

  // Simplified useEffect: only responsible for setting the default selected cluster for the UI.
  // The responsibility for updating the main validation summary is now in page.js.
  useEffect(() => {
    if (analysisResults && analysisResults['product-clustering']) {
      const summary = analysisResults['product-clustering'].clustering_results.cluster_summary;
      // Only set the default hot cluster if one hasn't been selected by the user yet.
      if (selectedCluster === null) {
        const hotCluster = summary.find(c => c.is_hot_cluster);
        if (hotCluster) {
          setSelectedCluster(hotCluster.cluster);
        }
      }
    }
  }, [analysisResults, selectedCluster]);

  // --- Memoized Calculations for UI ---

  // Efficiently filter the product list based on the user's selected cluster.
  const displayedProducts = useMemo(() => {
    if (!analysisResults || !analysisResults['product-clustering'] || selectedCluster === null) {
      return [];
    }
    const allProducts = analysisResults['product-clustering'].clustering_results.product_points;
    return allProducts
      .filter(p => p.cluster === selectedCluster)
      .sort((a, b) => b.total_amount - a.total_amount);
  }, [analysisResults, selectedCluster]);

  // --- Event Handlers ---

  // Handles API calls for analysis and updates parent state via callback.
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
      // Update parent component (page.js) with the new raw results.
      onValidationUpdate({ 
        results: { ...analysisResults, [endpoint]: result } 
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  };

  // --- Render Logic ---

  const renderTabContent = () => {
    switch (activeTab) {
      case 'forecast':
        if (analysisResults && analysisResults['forecast-sales']) {
            const figData = JSON.parse(analysisResults['forecast-sales']);
            return <Plot data={figData.data} layout={figData.layout} useResizeHandler={true} style={{ width: '100%', height: '100%' }} />;
        }
        return <button onClick={() => handleAnalysis('sales', salesFile, 'forecast-sales')} disabled={isLoading || !salesFile} className="btn-primary disabled:opacity-50">开始销售预测</button>;
      
      case 'clustering': {
        const clusteringData = analysisResults['product-clustering'];
        if (!clusteringData) {
          return <button onClick={() => handleAnalysis('sales', salesFile, 'product-clustering')} disabled={isLoading || !salesFile} className="btn-primary disabled:opacity-50">开始深度数据挖掘</button>;
        }

        const { clustering_results, basket_analysis_results } = clusteringData;
        const { elbow_data, product_points, cluster_summary } = clustering_results;

        return (
          <div className="space-y-12">
            <div>
              <h3 className="text-xl font-semibold text-white mb-4">K-Means 聚类分析</h3>
              <div className="bg-gray-800 p-4 rounded-lg mb-8">
                <h4 className="font-semibold text-white mb-2">手肘法确定最佳聚类数</h4>
                 <Plot
                  data={[{
                    x: elbow_data.map(d => d.k),
                    y: elbow_data.map(d => d.wcss),
                    type: 'scatter',
                    mode: 'lines+markers',
                    marker: { color: '#818cf8' },
                  }]}
                  layout={{ 
                    title: 'WCSS vs. 聚类数量 (K)',
                    xaxis: { title: '聚类数量 K' },
                    yaxis: { title: '簇内平方和 (WCSS)' },
                    template: 'plotly_dark'
                  }}
                  useResizeHandler={true}
                  style={{ width: '100%', height: '400px' }}
                />
                <p className="text-xs text-gray-400 mt-2">提示：“手肘”的拐点通常是最佳的K值。当曲线趋于平缓时，增加更多的簇带来的收益很小。</p>
              </div>

              <div className="bg-gray-800 p-4 rounded-lg mb-8">
                 <h4 className="font-semibold text-white mb-2">3D 聚类结果可视化</h4>
                 <Plot
                  data={[{
                    x: product_points.map(p => p.total_amount),
                    y: product_points.map(p => p.total_qty),
                    z: product_points.map(p => p.order_count),
                    text: product_points.map(p => p.SKU),
                    hoverinfo: 'x+y+z+text',
                    type: 'scatter3d',
                    mode: 'markers',
                    marker: { 
                      size: 5,
                      color: product_points.map(p => p.cluster),
                      colorscale: 'Viridis',
                      opacity: 0.8
                    },
                  }]}
                  layout={{
                    title: '产品分布3D视图',
                    template: 'plotly_dark',
                    scene: {
                      xaxis: { title: '总销售额' },
                      yaxis: { title: '总销量' },
                      zaxis: { title: '订单数' },
                    }
                  }}
                  useResizeHandler={true}
                  style={{ width: '100%', height: '500px' }}
                />
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
                  title={`簇 ${selectedCluster.toFixed(0)} 内的商品列表 (${displayedProducts.length} 条)`} 
                  data={displayedProducts} 
                />
              )}
            </div>

            <div className="border-t border-gray-700"></div>

            <div>
              <h3 className="text-xl font-semibold text-white mb-4">购物篮分析 (关联规则)</h3>
              {basket_analysis_results.length > 0 ? (
                <>
                  <p className="text-sm text-gray-400 mb-4">
                    挖掘出了哪些商品经常被一起购买。提升度(lift) &gt; 1 表示强关联性，是捆绑销售或交叉营销的绝佳机会。
                  </p>
                  <DataTable title="热门商品组合推荐" data={basket_analysis_results} />
                </>
              ) : (
                <p className="text-gray-400">在当前数据集中未发现显著的商品关联规则。</p>
              )}
            </div>
          </div>
        );
      }
      
      case 'sentiment':
        if (analysisResults && analysisResults['sentiment-analysis']) {
          return <SentimentAnalysis 
            analysisResult={analysisResults['sentiment-analysis']}
            aiReport={sentimentAiReport}
            setAiReport={(report) => onValidationUpdate({ sentimentReport: report })}
            isGenerating={isSentimentGenerating}
            setIsGenerating={setIsSentimentGenerating}
            error={sentimentError}
            setError={setSentimentError}
          />;
        }
        return <button onClick={() => handleAnalysis('reviews', reviewsFile, 'sentiment-analysis')} disabled={isLoading || !reviewsFile} className="btn-primary disabled:opacity-50">开始情感分析</button>;

      default:  
        return null;
    }
  };

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h3 className="text-lg font-medium text-white mb-2">1. 上传销售报告</h3>
          <FileUpload title="Amazon 销售报告 (.csv, .parquet)" onFileSelect={setSalesFile} isLoading={isLoading} />
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
            <button onClick={() => setActiveTab('sentiment')} className={`${activeTab === 'sentiment' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500'} whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}>
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