// frontend/app/page.js
'use client';

import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { visit } from 'unist-util-visit';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Bot, 
  ChevronRight, 
  MessageSquare, 
  Activity, 
  Sparkles,
  BarChart3,
  ShieldAlert,
  Search,
  Globe,
  ArrowRight,
  Monitor,
  ChevronDown
} from 'lucide-react';

import ProfileForm from './components/ProfileForm';
import ModernSidebar from './components/ModernSidebar';
import ModernHeader from './components/ModernHeader';
import CommandModal from './components/CommandModal';
import { SkeletonText } from './components/Skeleton';

import { useWorkflowState, useWorkflowActions, useWorkflowDerived } from '../contexts/WorkflowContext';
import { useStreamV2 } from '../hooks/useStreamV2';
import { API_BASE_URL } from '../lib/constants';

// --- Utils ---

function remarkAddTargetBlank() {
  return (tree) => {
    visit(tree, 'link', (node) => {
      node.data = node.data || {};
      node.data.hProperties = { target: '_blank', rel: 'noopener noreferrer' };
    });
  };
}

const AGENT_NAME_MAP = {
  trend_scout: '趋势侦察员',
  competitor_analyst: '竞品分析师',
  regulation_checker: '法规检查员',
  social_sentinel: '社媒哨兵',
  debate_challenger: '红队审查官',
  synthesizer: '综合分析师',
};

function displayAgentName(agentName = '') {
  return AGENT_NAME_MAP[agentName] || agentName;
}

function normalizeMarkdownText(rawText = '') {
  let text = String(rawText || '').trim();
  for (let i = 0; i < 2; i += 1) {
    const fencedMatch = text.match(/^```(?:markdown|md|mdx|text)?\s*\n?([\s\S]*?)\n?```$/i);
    if (fencedMatch) text = (fencedMatch[1] || '').trim();
  }
  return text;
}

// --- Components ---

function MarkdownBlock({ content, className }) {
  const normalized = normalizeMarkdownText(content);
  if (!normalized) return null;
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkAddTargetBlank]}>
        {normalized}
      </ReactMarkdown>
    </div>
  );
}

function CustomSelect({ value, onChange, options, disabled }) {
  const [isOpen, setIsOpen] = useState(false);
  const selectedLabel = options.find(opt => opt.value === value)?.label || value;

  return (
    <div className="relative">
      <button
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border bg-background/50 hover:bg-accent/50 transition-colors text-xs font-bold text-foreground ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        {selectedLabel}
        <ChevronDown size={12} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      <AnimatePresence>
        {isOpen && (
          <>
            <div 
              className="fixed inset-0 z-40" 
              onClick={() => setIsOpen(false)} 
            />
            <motion.div
              initial={{ opacity: 0, y: -5, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -5, scale: 0.95 }}
              className="absolute right-0 top-full mt-2 w-48 z-50 glass rounded-xl border border-border shadow-xl overflow-hidden p-1 flex flex-col gap-0.5"
            >
              {options.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => {
                    onChange(opt.value);
                    setIsOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                    value === opt.value 
                      ? 'bg-accent text-accent-foreground' 
                      : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

function AgentCard({ agentName, result }) {
  const status = result?.status || 'pending';
  const isRunning = status === 'running';
  
  const statusStyles = {
    completed: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
    running: 'bg-gemini-blue/10 text-gemini-blue border-gemini-blue/20 animate-pulse',
    failed: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20',
    pending: 'bg-muted/10 text-muted-foreground border-border',
    degraded: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
    skipped: 'bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/20',
  };

  const currentStatusStyle = statusStyles[status] || statusStyles.pending;
  
  return (
    <motion.div 
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="group relative rounded-2xl border border-border bg-card p-5 transition-all hover:shadow-xl hover:shadow-gemini-blue/5 overflow-hidden"
    >
      {isRunning && (
        <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-gemini-blue via-gemini-purple to-gemini-red animate-shimmer" style={{ backgroundSize: '200% 100%' }} />
      )}
      
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg transition-colors ${isRunning ? 'bg-gemini-blue/10 text-gemini-blue' : 'bg-accent/50 text-muted-foreground'}`}>
            <Bot size={18} />
          </div>
          <h3 className="font-bold text-foreground tracking-tight">{displayAgentName(agentName)}</h3>
        </div>
        <div className={`text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-full border ${currentStatusStyle}`}>
          {status}
        </div>
      </div>

      {result?.thinking && (isRunning || status === 'completed') && (
        <details className="mb-4 rounded-xl border border-border bg-accent/20 overflow-hidden">
          <summary className="px-3 py-2 text-[10px] font-bold uppercase tracking-tighter text-muted-foreground cursor-pointer hover:bg-accent/50 transition-colors flex items-center gap-2 select-none">
            <Activity size={12} /> 思考路径 (Thinking)
          </summary>
          <div className="px-3 pb-3 pt-0 text-[11px] leading-relaxed text-muted-foreground/80 font-mono overflow-x-auto">
            {result.thinking}
          </div>
        </details>
      )}

      {result?.content ? (
        <MarkdownBlock
          content={result.content}
          className="prose prose-sm dark:prose-invert max-w-none transition-all duration-500"
        />
      ) : isRunning ? (
        <div className="space-y-2 py-2">
          <div className="h-2 w-full bg-accent rounded-full animate-pulse" />
          <div className="h-2 w-[90%] bg-accent rounded-full animate-pulse delay-75" />
          <div className="h-2 w-[70%] bg-accent rounded-full animate-pulse delay-150" />
        </div>
      ) : (
        <p className="text-xs text-muted-foreground italic">等待任务分配...</p>
      )}
    </motion.div>
  );
}

function DebateTheater({ exchanges }) {
  return (
    <div className="space-y-6">
      <AnimatePresence initial={false}>
        {exchanges.map((ex, idx) => {
          const isRedTeam = ex.challenger === 'debate_challenger';
          return (
            <motion.div
              key={`${ex.roundNumber}-${ex.challenger}-${idx}`}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className={`relative grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-4 items-start`}
            >
              {/* Challenger */}
              <div className="glass rounded-2xl p-5 border-l-4 border-gemini-blue shadow-sm">
                <div className="flex items-center gap-2 mb-3 text-xs font-bold text-gemini-blue uppercase">
                  <Sparkles size={12} /> {displayAgentName(ex.challenger)} 的质疑
                </div>
                <MarkdownBlock content={ex.challengeContent} className="prose prose-sm dark:prose-invert max-w-none" />
              </div>

              {/* Direction Indicator */}
              <div className="hidden md:flex flex-col items-center justify-center h-full py-8 text-muted-foreground/30">
                <div className="h-full w-[1px] bg-gradient-to-b from-transparent via-border to-transparent" />
                <ArrowRight size={20} className="my-2" />
                <div className="h-full w-[1px] bg-gradient-to-b from-transparent via-border to-transparent" />
              </div>

              {/* Responder */}
              <div className="glass rounded-2xl p-5 border-l-4 border-gemini-purple shadow-sm">
                <div className="flex items-center gap-2 mb-3 text-xs font-bold text-gemini-purple uppercase">
                  <MessageSquare size={12} /> {displayAgentName(ex.responder)} 的回应
                </div>
                <MarkdownBlock content={ex.responseContent} className="prose prose-sm dark:prose-invert max-w-none" />
                {ex.revised && (
                  <div className="mt-3 inline-flex items-center gap-1.5 px-2 py-1 rounded bg-amber-500/10 border border-amber-500/20 text-[10px] font-bold text-amber-600 dark:text-amber-400 uppercase">
                    <Activity size={10} /> 观点已修正
                  </div>
                )}
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

// --- Main Page ---

export default function Home() {
  const state = useWorkflowState();
  const actions = useWorkflowActions();
  const derived = useWorkflowDerived();
  const { startStream, stopStream } = useStreamV2();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [debateRounds, setDebateRounds] = useState(2);

  const { userProfile, isGenerating, synthesizedReport, reportHtmlUrl, error } = state;
  const toolMetrics = state.toolMetrics;

  const agentEntries = useMemo(() => Object.entries(state.agentResults || {}), [state.agentResults]);
  const sortedDebates = useMemo(() => {
    const debates = Array.isArray(state.debateExchanges) ? state.debateExchanges : [];
    return [...debates].sort((a, b) => (a.roundNumber || 0) - (b.roundNumber || 0));
  }, [state.debateExchanges]);
  const agentToolMetrics = useMemo(() => {
    const rows = toolMetrics?.by_agent && typeof toolMetrics.by_agent === 'object'
      ? Object.entries(toolMetrics.by_agent)
      : [];
    return rows.sort((a, b) => (b[1]?.total_calls || 0) - (a[1]?.total_calls || 0));
  }, [toolMetrics]);

  const resolvedReportHtmlUrl = useMemo(() => {
    if (!reportHtmlUrl) return '';
    return reportHtmlUrl.startsWith('http') ? reportHtmlUrl : `${API_BASE_URL}${reportHtmlUrl}`;
  }, [reportHtmlUrl]);

  const handleStart = async () => {
    if (!userProfile || isGenerating) return;
    actions.clearError();
    await startStream({ profile: userProfile, enableWebsearch: state.enableWebsearch, debateRounds });
  };

  if (!userProfile) {
    return (
      <main className="min-h-screen bg-background flex flex-col items-center justify-center p-6 relative overflow-hidden">
        {/* 背景装饰 */}
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-gemini-blue/10 rounded-full blur-[120px] animate-pulse-gemini" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-gemini-red/10 rounded-full blur-[120px] animate-pulse-gemini" style={{ animationDelay: '2s' }} />

        <motion.div 
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="relative z-10 text-center max-w-2xl"
        >
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass border border-border mb-8 text-sm font-medium text-muted-foreground">
            <Sparkles size={16} className="text-gemini-blue" />
            下一代多 Agent 市场洞察系统
          </div>
          <h1 className="text-6xl md:text-7xl font-bold tracking-tighter mb-6 text-foreground">
            Weave<span className="gemini-text italic pr-4 -mr-2">AI</span> 2.0
          </h1>
          <p className="text-lg text-muted-foreground mb-12 max-w-lg mx-auto leading-relaxed">
            利用 Supervisor-Worker 架构与多轮辩论机制，深度挖掘全球市场趋势与竞争格局。
          </p>
          
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={() => setIsModalOpen(true)}
              className="px-10 py-5 text-lg font-bold text-white bg-foreground dark:bg-foreground dark:text-background rounded-2xl hover:scale-105 active:scale-95 transition-all shadow-xl shadow-foreground/10"
            >
              创建战略档案
            </button>
            <div className="flex items-center gap-2 text-sm text-muted-foreground font-medium px-4">
              <Monitor size={16} /> 体验灵动的科技美学
            </div>
          </div>
        </motion.div>

        <CommandModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)}>
          <ProfileForm onFormSubmit={(p) => { setIsModalOpen(false); actions.setProfile(p); }} isLoading={isGenerating} />
        </CommandModal>
      </main>
    );
  }

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <ModernSidebar profile={userProfile} onReset={() => actions.resetSession()} isGenerating={isGenerating} />
      
      <main className="flex-grow flex flex-col min-w-0 relative">
        <ModernHeader isGenerating={isGenerating} onDownload={resolvedReportHtmlUrl ? () => window.open(resolvedReportHtmlUrl + '?download=1', '_blank') : null} />
        
        <div className="flex-grow overflow-y-auto p-6 md:p-10 space-y-12 max-w-7xl mx-auto w-full">
          
          {/* Bento Section 1: Progress & Context */}
          <section>
            <div className="flex items-center gap-2 mb-6">
              <Activity size={20} className="text-gemini-blue" />
              <h2 className="text-2xl font-bold tracking-tight">执行进度</h2>
              <div className="h-px flex-grow bg-border ml-4" />
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {['trend_scout', 'competitor_analyst', 'regulation_checker', 'social_sentinel'].map((name) => (
                <AgentCard key={name} agentName={name} result={state.agentResults[name]} />
              ))}
            </div>
            
            {error && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-6 p-4 rounded-2xl bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 text-sm flex items-center gap-3">
                <Activity size={18} /> {error}
              </motion.div>
            )}
          </section>

          {/* Bento Section 2: Debate Theater */}
          <section>
            <div className="flex items-center gap-2 mb-8">
              <MessageSquare size={20} className="text-gemini-purple" />
              <h2 className="text-2xl font-bold tracking-tight">辩论剧场 (Debate Theater)</h2>
              <div className="h-px flex-grow bg-border ml-4" />
              
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold text-muted-foreground uppercase hidden sm:inline">轮数设定</span>
                <CustomSelect
                  value={debateRounds}
                  onChange={(val) => setDebateRounds(val)}
                  disabled={isGenerating}
                  options={[
                    { value: 0, label: '0 (直达综合)' },
                    { value: 1, label: '1 (同行评审)' },
                    { value: 2, label: '2 (红队审查)' },
                  ]}
                />
              </div>
            </div>

            {debateRounds === 0 ? (
              <div className="py-12 text-center glass rounded-3xl border border-dashed border-border text-muted-foreground italic">
                当前跳过了辩论流程。
              </div>
            ) : sortedDebates.length > 0 ? (
              <DebateTheater exchanges={sortedDebates} />
            ) : isGenerating ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8 py-12">
                <SkeletonText lines={6} className="glass p-6 rounded-3xl" />
                <SkeletonText lines={6} className="glass p-6 rounded-3xl" />
              </div>
            ) : (
              <div className="py-12 text-center glass rounded-3xl border border-dashed border-border text-muted-foreground italic">
                等待辩论开始...
              </div>
            )}
          </section>

          {/* Bento Section 3: Tool Metrics */}
          <section>
            <div className="flex items-center gap-2 mb-8">
              <BarChart3 size={20} className="text-gemini-blue" />
              <h2 className="text-2xl font-bold tracking-tight">成本与稳定性</h2>
              <div className="h-px flex-grow bg-border ml-4" />
            </div>

            {toolMetrics?.session ? (
              <div className="space-y-6">
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  <div className="glass rounded-2xl border border-border p-4">
                    <div className="text-xs text-muted-foreground">总工具调用</div>
                    <div className="text-2xl font-bold tracking-tight">{toolMetrics.session.total_calls || 0}</div>
                  </div>
                  <div className="glass rounded-2xl border border-border p-4">
                    <div className="text-xs text-muted-foreground">错误率</div>
                    <div className="text-2xl font-bold tracking-tight">{((toolMetrics.session.error_rate || 0) * 100).toFixed(1)}%</div>
                  </div>
                  <div className="glass rounded-2xl border border-border p-4">
                    <div className="text-xs text-muted-foreground">平均时延</div>
                    <div className="text-2xl font-bold tracking-tight">{Math.round(toolMetrics.session.avg_duration_ms || 0)}ms</div>
                  </div>
                  <div className="glass rounded-2xl border border-border p-4">
                    <div className="text-xs text-muted-foreground">估算成本</div>
                    <div className="text-2xl font-bold tracking-tight">${(toolMetrics.session.total_estimated_cost_usd || 0).toFixed(4)}</div>
                  </div>
                  <div className="glass rounded-2xl border border-border p-4">
                    <div className="text-xs text-muted-foreground">缓存命中率</div>
                    <div className="text-2xl font-bold tracking-tight">{((toolMetrics.session.cache_hit_rate || 0) * 100).toFixed(1)}%</div>
                  </div>
                </div>

                <div className="glass rounded-2xl border border-border overflow-hidden">
                  <div className="flex items-center gap-2 px-4 py-3 border-b border-border text-sm font-bold">
                    <ShieldAlert size={14} className="text-gemini-red" /> Agent 维度
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-xs text-muted-foreground uppercase tracking-wider">
                        <tr>
                          <th className="text-left px-4 py-3">Agent</th>
                          <th className="text-right px-4 py-3">调用</th>
                          <th className="text-right px-4 py-3">错误率</th>
                          <th className="text-right px-4 py-3">平均时延</th>
                          <th className="text-right px-4 py-3">估算成本</th>
                        </tr>
                      </thead>
                      <tbody>
                        {agentToolMetrics.map(([agentName, row]) => (
                          <tr key={agentName} className="border-t border-border/60">
                            <td className="px-4 py-3 font-medium">{displayAgentName(agentName)}</td>
                            <td className="px-4 py-3 text-right">{row?.total_calls || 0}</td>
                            <td className="px-4 py-3 text-right">{(((row?.error_rate || 0) * 100)).toFixed(1)}%</td>
                            <td className="px-4 py-3 text-right">{Math.round(row?.avg_duration_ms || 0)}ms</td>
                            <td className="px-4 py-3 text-right">${(row?.total_estimated_cost_usd || 0).toFixed(4)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-10 text-center glass rounded-3xl border border-dashed border-border text-muted-foreground italic">
                暂无工具层指标，生成一次任务后将自动展示。
              </div>
            )}
          </section>

          {/* Bento Section 4: Final Synthesis */}
          <section className="pb-20">
            <div className="flex items-center gap-2 mb-8">
              <Sparkles size={20} className="text-gemini-red" />
              <h2 className="text-2xl font-bold tracking-tight">综合洞察报告</h2>
              <div className="h-px flex-grow bg-border ml-4" />
            </div>

            {synthesizedReport ? (
              <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="relative group"
              >
                <div className="absolute -inset-1 bg-gradient-to-r from-gemini-blue via-gemini-purple to-gemini-red rounded-[2rem] blur opacity-10 group-hover:opacity-20 transition duration-1000" />
                <div className="relative glass rounded-[2rem] border border-border p-8 md:p-12 shadow-2xl">
                  <MarkdownBlock content={synthesizedReport} className="prose prose-lg dark:prose-invert max-w-none prose-headings:tracking-tighter prose-p:leading-relaxed" />
                </div>
              </motion.div>
            ) : isGenerating ? (
              <div className="glass rounded-[2rem] p-12 border border-border">
                <div className="flex items-center gap-4 mb-8">
                  <div className="w-10 h-10 rounded-full bg-accent animate-pulse" />
                  <div className="space-y-2">
                    <div className="h-4 w-48 bg-accent rounded-full animate-pulse" />
                    <div className="h-3 w-32 bg-accent rounded-full animate-pulse opacity-60" />
                  </div>
                </div>
                <SkeletonText lines={12} />
              </div>
            ) : (
              <div className="py-20 text-center glass rounded-[2rem] border border-dashed border-border text-muted-foreground italic text-lg">
                完成上述分析后，综合报告将在此呈现。
              </div>
            )}
          </section>

        </div>

        {/* Start Button Overlay for generating */}
        {!isGenerating && !synthesizedReport && userProfile && (
           <motion.div 
            initial={{ y: 50, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            className="absolute bottom-8 left-1/2 -translate-x-1/2 z-30"
           >
              <button
                onClick={handleStart}
                className="group flex items-center gap-3 px-8 py-4 bg-foreground text-background dark:bg-foreground dark:text-background rounded-full font-bold text-lg hover:scale-105 active:scale-95 transition-all shadow-2xl shadow-foreground/20"
              >
                开始编排分析
                <div className="p-1 rounded-full bg-background/20 group-hover:translate-x-1 transition-transform">
                  <ChevronRight size={18} />
                </div>
              </button>
           </motion.div>
        )}
      </main>

      <CommandModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)}>
        <ProfileForm onFormSubmit={(p) => { setIsModalOpen(false); actions.setProfile(p); }} isLoading={isGenerating} />
      </CommandModal>
    </div>
  );
}
