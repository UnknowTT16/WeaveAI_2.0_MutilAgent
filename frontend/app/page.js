// frontend/app/page.js
'use client';

import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { visit } from 'unist-util-visit';

import ProfileForm from './components/ProfileForm';
import ProfileSidebar from './components/ProfileSidebar';
import CommandModal from './components/CommandModal';
import { SkeletonText } from './components/Skeleton';

import { useWorkflowState, useWorkflowActions, useWorkflowDerived } from '../contexts/WorkflowContext';
import { useStreamV2 } from '../hooks/useStreamV2';

function remarkAddTargetBlank() {
  return (tree) => {
    visit(tree, 'link', (node) => {
      node.data = node.data || {};
      node.data.hProperties = { target: '_blank', rel: 'noopener noreferrer' };
    });
  };
}

function AgentCard({ agentName, result }) {
  const status = result?.status || 'pending';
  const statusText = status === 'running' ? '进行中' : status === 'completed' ? '已完成' : status === 'failed' ? '失败' : '等待中';
  const statusColor = status === 'running'
    ? 'bg-amber-900/40 text-amber-200 border-amber-700'
    : status === 'completed'
      ? 'bg-emerald-900/30 text-emerald-200 border-emerald-700'
      : status === 'failed'
        ? 'bg-red-900/30 text-red-200 border-red-700'
        : 'bg-gray-900/30 text-gray-300 border-gray-700';

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="font-semibold text-white">{agentName}</div>
        <div className={`text-xs px-2 py-1 rounded border ${statusColor}`}>{statusText}</div>
      </div>
      {result?.error ? (
        <div className="mt-3 text-sm text-red-200">{result.error}</div>
      ) : null}
      {result?.content ? (
        <div className="mt-3 text-sm text-gray-300 whitespace-pre-wrap">{result.content}</div>
      ) : null}
      {status === 'running' && !result?.content ? (
        <div className="mt-3"><SkeletonText lines={3} /></div>
      ) : null}
    </div>
  );
}

export default function Home() {
  const state = useWorkflowState();
  const actions = useWorkflowActions();
  const derived = useWorkflowDerived();
  const { startStream, stopStream } = useStreamV2();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [debateRounds, setDebateRounds] = useState(2);

  const userProfile = state.userProfile;
  const isGenerating = state.isGenerating;
  const enableWebsearch = state.enableWebsearch;
  const report = state.synthesizedReport;
  const error = state.error;

  const agentEntries = useMemo(() => Object.entries(state.agentResults || {}), [state.agentResults]);

  const handleProfileSubmit = (profile) => {
    setIsModalOpen(false);
    actions.setProfile(profile);
  };

  const handleReset = () => {
    actions.resetSession();
  };

  const handleStart = async () => {
    if (!userProfile || isGenerating) return;
    actions.clearError();
    await startStream({
      profile: userProfile,
      enableWebsearch,
      debateRounds,
    });
  };

  return (
    <main className="min-h-screen bg-gray-900 text-gray-300 flex flex-col">
      {userProfile ? (
        <>
          <header className="text-center py-6 border-b border-gray-800 flex-shrink-0">
            <h1 className="text-3xl font-bold text-white">WeaveAI 2.0 多 Agent 市场洞察</h1>
            <p className="text-gray-400 mt-2 text-sm">Supervisor-Worker + 多轮辩论 + SSE 实时流</p>
          </header>

          <div className="flex-grow flex overflow-hidden">
            <aside className="w-72 flex-shrink-0 p-6 border-r border-gray-800 overflow-y-auto">
              <ProfileSidebar profile={userProfile} onReset={handleReset} />
              <div className="mt-6 rounded-lg border border-gray-800 bg-gray-800/40 p-4">
                <div className="text-sm text-gray-400">运行参数</div>

                <div className="mt-3 flex items-center justify-between gap-3">
                  <div className="text-sm">联网搜索</div>
                  <button
                    type="button"
                    onClick={() => actions.toggleWebsearch()}
                    disabled={isGenerating}
                    className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${
                      enableWebsearch
                        ? 'bg-emerald-600/20 text-emerald-200 border-emerald-700 hover:bg-emerald-600/30'
                        : 'bg-gray-900/30 text-gray-200 border-gray-700 hover:bg-gray-900/50'
                    } ${isGenerating ? 'opacity-60 cursor-not-allowed' : ''}`}
                  >
                    {enableWebsearch ? '已开启' : '已关闭'}
                  </button>
                </div>

                <div className="mt-3 flex items-center justify-between gap-3">
                  <div className="text-sm">辩论轮数</div>
                  <select
                    value={debateRounds}
                    onChange={(e) => setDebateRounds(parseInt(e.target.value, 10))}
                    disabled={isGenerating}
                    className="bg-gray-900/40 border border-gray-700 rounded-md px-2 py-1.5 text-sm text-gray-200"
                  >
                    <option value={0}>0</option>
                    <option value={1}>1</option>
                    <option value={2}>2</option>
                  </select>
                </div>

                <div className="mt-4 flex flex-col gap-2">
                  <button
                    type="button"
                    onClick={handleStart}
                    disabled={isGenerating}
                    className="w-full inline-flex items-center justify-center px-4 py-2 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {isGenerating ? '分析进行中...' : '开始分析'}
                  </button>
                  <button
                    type="button"
                    onClick={stopStream}
                    disabled={!isGenerating}
                    className="w-full inline-flex items-center justify-center px-4 py-2 rounded-lg text-sm font-semibold bg-gray-700 hover:bg-gray-600 text-white transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    停止
                  </button>
                </div>

                <div className="mt-4 text-xs text-gray-400">
                  已完成 Agent：{derived.completedAgents}/{derived.totalAgents || 4}
                </div>
              </div>
            </aside>

            <div className="flex-grow p-6 md:p-8 overflow-y-auto">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-gray-800 rounded-lg shadow-lg p-6">
                  <h2 className="text-xl font-semibold text-white mb-4">执行进度</h2>
                  <div className="grid grid-cols-1 gap-4">
                    {agentEntries.length === 0 ? (
                      <div className="text-sm text-gray-400">尚未开始，点击左侧“开始分析”。</div>
                    ) : (
                      agentEntries.map(([agentName, result]) => (
                        <AgentCard key={agentName} agentName={agentName} result={result} />
                      ))
                    )}
                  </div>
                  {error ? (
                    <div className="mt-4 text-red-200 bg-red-900/30 border border-red-700 p-4 rounded-md text-sm">{error}</div>
                  ) : null}
                </div>

                <div className="bg-gray-800 rounded-lg shadow-lg p-6">
                  <h2 className="text-xl font-semibold text-white mb-4">综合报告</h2>
                  {isGenerating && !report ? (
                    <SkeletonText lines={10} />
                  ) : report ? (
                    <div className="prose prose-invert max-w-none bg-gray-900/50 p-6 rounded-lg">
                      <ReactMarkdown remarkPlugins={[remarkGfm, remarkAddTargetBlank]}>{report}</ReactMarkdown>
                    </div>
                  ) : (
                    <div className="text-sm text-gray-400">报告会在工作流完成后自动出现。</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="flex-grow flex items-center justify-center p-4">
          <div className="text-center max-w-2xl w-full">
            <div className="mb-8">
              <h1 className="text-4xl md:text-5xl font-bold text-white">WeaveAI 2.0</h1>
              <p className="text-gray-400 mt-4 text-lg">多 Agent 市场洞察与辩论式综合报告</p>
            </div>
            <div className="bg-gray-800/50 rounded-xl p-8 shadow-2xl border border-gray-700">
              <h2 className="text-2xl font-bold text-white mb-4">创建战略档案</h2>
              <p className="text-gray-400 mb-8">填写目标市场、品类与价格区间，即可开始多 Agent 协作分析。</p>
              <button
                onClick={() => setIsModalOpen(true)}
                className="px-8 py-4 text-lg font-bold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-transform transform hover:scale-105 shadow-lg shadow-indigo-600/30"
              >
                开始
              </button>
            </div>
          </div>
        </div>
      )}

      <CommandModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)}>
        <ProfileForm onFormSubmit={handleProfileSubmit} isLoading={isGenerating} />
      </CommandModal>
    </main>
  );
}
