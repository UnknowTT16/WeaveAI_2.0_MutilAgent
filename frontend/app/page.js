'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { visit } from 'unist-util-visit';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Download,
  Eye,
  FileText,
  History,
  LayoutGrid,
  ListChecks,
  Search,
  Settings2,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react';

import ProfileForm, {
  DEFAULT_PROFILE_DRAFT,
  normalizeProfileDraft,
} from './components/ProfileForm';
import ModernSidebar from './components/ModernSidebar';
import ModernHeader from './components/ModernHeader';
import VegaLiteCharts from './components/VegaLiteCharts';

import { useWorkflowState, useWorkflowActions } from '../contexts/WorkflowContext';
import { useStreamV2 } from '../hooks/useStreamV2';
import { API_BASE_URL, API_ENDPOINTS } from '../lib/constants';
import {
  DEMO_PRESETS,
  DEFAULT_DEMO_PRESET_ID,
  getDemoPresetById,
} from '../lib/demoPresets';
import {
  getDefaultAnalysisPreferences,
  loadAnalysisPreferences,
  saveAnalysisPreferences,
  sanitizeAnalysisPreferences,
} from '../lib/analysisPreferences';

const HISTORY_PAGE_SIZE = 12;

const AGENT_NAME_MAP = {
  trend_scout: '趋势研究',
  competitor_analyst: '竞品对比',
  regulation_checker: '合规检查',
  social_sentinel: '社媒反馈',
  debate_challenger: '交叉质询',
  synthesizer: '结论整合',
};

const AGENT_PIPELINE = [
  'trend_scout',
  'competitor_analyst',
  'regulation_checker',
  'social_sentinel',
  'synthesizer',
];

const TASK_TEMPLATES = [
  {
    id: 'new_product',
    label: '新品选品',
    profile: {
      target_market: '德国',
      supply_chain: '家居收纳',
      seller_type: '品牌方',
      min_price: 20,
      max_price: 60,
    },
  },
  {
    id: 'competitor_scan',
    label: '竞品扫描',
    profile: {
      target_market: '美国',
      supply_chain: '消费电子',
      seller_type: '贸易商',
      min_price: 30,
      max_price: 120,
    },
  },
  {
    id: 'risk_check',
    label: '风险检查',
    profile: {
      target_market: '日本',
      supply_chain: '美妆个护',
      seller_type: '工厂转型',
      min_price: 15,
      max_price: 80,
    },
  },
];

function remarkAddTargetBlank() {
  return (tree) => {
    visit(tree, 'link', (node) => {
      node.data = node.data || {};
      node.data.hProperties = { target: '_blank', rel: 'noopener noreferrer' };
    });
  };
}

function isMarkdownTableLine(line = '') {
  const text = String(line || '').trim();
  if (!text || !text.includes('|')) return false;
  return text.startsWith('|') || text.endsWith('|');
}

function isMarkdownTableDivider(line = '') {
  const text = String(line || '').trim();
  if (!text || !text.includes('-')) return false;
  const cleaned = text.replace(/[|:\-\s]/g, '');
  return cleaned.length === 0;
}

function normalizeGfmTables(markdown = '') {
  const source = String(markdown || '').replace(/｜/g, '|');
  const lines = source.split('\n');
  const output = [];

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const next = i + 1 < lines.length ? lines[i + 1] : '';
    const prevOutput = output.length > 0 ? output[output.length - 1] : '';

    const tableStartsHere = isMarkdownTableLine(line) && isMarkdownTableDivider(next);
    if (tableStartsHere && String(prevOutput).trim() !== '') {
      output.push('');
    }

    output.push(line);

    const tableEndsHere = isMarkdownTableLine(line) && !isMarkdownTableLine(next);
    if (tableEndsHere && next && String(next).trim() !== '') {
      output.push('');
    }
  }

  return output.join('\n');
}

function normalizeMarkdownText(rawText = '') {
  let text = String(rawText || '').trim();
  for (let i = 0; i < 2; i += 1) {
    const fencedMatch = text.match(/^```(?:markdown|md|mdx|text)?\s*\n?([\s\S]*?)\n?```$/i);
    if (fencedMatch) text = (fencedMatch[1] || '').trim();
  }
  text = normalizeGfmTables(text);
  return text;
}

function composeDebateMarkdown(exchange) {
  if (!exchange || typeof exchange !== 'object') return '';

  const challenge = normalizeMarkdownText(exchange.challengeContent || '');
  const response = normalizeMarkdownText(exchange.responseContent || '');
  const followup = normalizeMarkdownText(exchange.followupContent || '');

  const blocks = [];
  if (challenge) blocks.push(`### 质疑内容\n\n${challenge}`);
  if (response) blocks.push(`### 回应内容\n\n${response}`);
  if (followup) blocks.push(`### 二次追问\n\n${followup}`);

  return blocks.join('\n\n---\n\n');
}

function extractTopConclusions(markdown = '', max = 3) {
  const text = normalizeMarkdownText(markdown);
  if (!text) return [];

  const lines = text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

  const bullets = lines
    .filter((line) => /^[-*+]\s+/.test(line) || /^\d+\.\s+/.test(line))
    .map((line) => line.replace(/^[-*+\d.\s]+/, '').trim())
    .filter(Boolean);

  if (bullets.length >= max) return bullets.slice(0, max);

  const plain = lines
    .filter((line) => !line.startsWith('#'))
    .filter((line) => !/^[-*+]\s+/.test(line) && !/^\d+\.\s+/.test(line))
    .map((line) => line.replace(/^>\s*/, '').trim())
    .filter(Boolean);

  return [...bullets, ...plain].slice(0, max);
}

function formatDuration(ms) {
  const value = Number(ms);
  if (!Number.isFinite(value) || value <= 0) return '--';
  if (value < 1000) return `${Math.round(value)}ms`;
  if (value < 60_000) return `${(value / 1000).toFixed(1)}s`;
  const minutes = Math.floor(value / 60_000);
  const seconds = Math.round((value % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

function formatDateTime(value) {
  if (!value) return '--';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return '--';
  return dt.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function sessionStatusLabel(status) {
  const s = String(status || '').toLowerCase();
  const map = {
    running: '进行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  };
  return map[s] || (status || '未知');
}

function recoveryReasonLabel(reason) {
  const value = String(reason || 'stream_interrupted').toLowerCase();
  const map = {
    stream_idle_timeout: '连接长时间无更新',
    stream_ended_while_running: '连接提前结束',
    stream_exception: '连接异常',
    stream_interrupted: '连接中断',
  };
  return map[value] || '连接中断';
}

function displayAgentName(agentName = '') {
  return AGENT_NAME_MAP[agentName] || agentName;
}

function buildActionSuggestions(demoMetrics, recovery, toolMetrics) {
  const evidenceRate = Number(demoMetrics?.evidence_coverage_rate || 0);
  const stabilityScore = Number(demoMetrics?.stability_score || 0);
  const failCount = Number(demoMetrics?.failed_agents || 0);
  const retryCount = Number(demoMetrics?.retry_count || 0);
  const estimatedCost = Number(toolMetrics?.session?.total_estimated_cost_usd || 0);

  const riskText = failCount > 0 || recovery?.mode === 'timeout'
    ? '发现流程波动，建议先补齐高风险环节再扩大投放。'
    : '当前流程稳定，可进入下一轮验证。';

  return [
    {
      title: '优先级排序',
      content: `高优：先验证转化路径；中优：补齐证据链；低优：优化展示文案。`,
    },
    {
      title: '风险提醒',
      content: `${riskText}（重试 ${retryCount} 次）`,
    },
    {
      title: '投入与回报预估',
      content: `本次分析耗时 ${formatDuration(demoMetrics?.total_duration_ms)}，估算成本 $${estimatedCost.toFixed(4)}。`,
    },
    {
      title: '角色化建议',
      content: evidenceRate >= 0.75 && stabilityScore >= 80
        ? '老板看结论与节奏，运营拿行动清单，产品按图表验证假设。'
        : '老板先看风险，运营先补样本，产品先校准指标口径。',
    },
  ];
}

function MarkdownBlock({ content, className = '' }) {
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

function SectionTitle({ icon: Icon, title, subtitle }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div>
        <div className="flex items-center gap-2">
          <Icon size={18} className="text-gemini-blue" aria-hidden="true" />
          <h2 className="section-title">{title}</h2>
        </div>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
    </div>
  );
}

function LabeledSelect({ id, label, value, onChange, options, disabled = false }) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        className="h-10 rounded-xl border border-border bg-background px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function WebsearchToggle({ enabled, disabled = false, onToggle }) {
  return (
    <div className="rounded-xl border border-border bg-background px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-muted-foreground">联网搜索</p>
          <p className={`mt-1 text-sm ${enabled ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>
            {enabled ? '已开启（结果更新鲜）' : '已关闭（默认，速度更快）'}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">开启后会调用 web_search，耗时和成本会增加。</p>
        </div>

        <button
          type="button"
          onClick={onToggle}
          disabled={disabled}
          aria-pressed={enabled}
          aria-label={enabled ? '关闭联网搜索' : '开启联网搜索'}
          className={`inline-flex h-9 items-center gap-1 rounded-lg border px-3 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${enabled ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'border-border text-foreground hover:bg-accent/70'}`}
        >
          <Search size={12} aria-hidden="true" />
          {enabled ? '已开启' : '已关闭'}
        </button>
      </div>
    </div>
  );
}

function ProgressStepList({ rows }) {
  return (
    <ol className="space-y-2">
      {rows.map((row, index) => (
        <li key={row.key} className="flex items-center justify-between rounded-xl border border-border bg-background px-3 py-2.5 text-sm">
          <div className="flex items-center gap-2">
            <span className="numeric inline-flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[11px] text-muted-foreground">
              {index + 1}
            </span>
            <span>{row.label}</span>
          </div>
          <span className={`status-pill ${row.tone}`}>{row.statusLabel}</span>
        </li>
      ))}
    </ol>
  );
}

function ProfessionalProgress({ rows, onOpenThinking, onOpenReport }) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {rows.map((row) => (
        <article key={row.key} className="rounded-xl border border-border bg-background p-3">
          <div className="mb-1 flex items-center justify-between gap-3 text-sm">
            <span className="font-medium text-foreground">{row.label}</span>
            <span className={`status-pill ${row.tone}`}>{row.statusLabel}</span>
          </div>
          <div className="text-xs text-muted-foreground">
            {row.error ? `提示：${row.error}` : row.durationText}
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">
              {row.thinking
                ? `已生成思考内容（${row.thinking.length} 字）`
                : row.status === 'running'
                  ? '思考生成中，可随时查看'
                  : '暂无思考内容'}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => onOpenThinking?.(row.key)}
                className="h-8 rounded-lg border border-border px-3 text-xs font-medium text-foreground transition-colors hover:bg-accent/70"
              >
                展开思考
              </button>
              <button
                type="button"
                onClick={() => onOpenReport?.(row.key)}
                className="h-8 rounded-lg border border-border px-3 text-xs font-medium text-foreground transition-colors hover:bg-accent/70"
              >
                查看报告
              </button>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function AgentThinkingModal({ row, isOpen, onClose }) {
  useEffect(() => {
    if (!isOpen) return undefined;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onEsc = (event) => {
      if (event.key === 'Escape') {
        onClose?.();
      }
    };

    window.addEventListener('keydown', onEsc);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener('keydown', onEsc);
    };
  }, [isOpen, onClose]);

  if (!isOpen || !row) return null;

  const thinking = String(row.thinking || '').trim();

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4" role="presentation">
      <button
        type="button"
        aria-label="关闭思考浮窗"
        onClick={onClose}
        className="absolute inset-0 bg-background/75 backdrop-blur-sm"
      />
      <section
        role="dialog"
        aria-modal="true"
        aria-label={`${row.label} 的思考过程`}
        className="relative z-[111] w-full max-w-3xl rounded-2xl border border-border bg-card shadow-2xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div>
            <h3 className="text-base font-semibold text-foreground">{row.label} · 思考过程</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              状态：{row.statusLabel} · {row.error ? `提示：${row.error}` : row.durationText}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border p-2 text-muted-foreground transition-colors hover:bg-accent/70 hover:text-foreground"
            aria-label="关闭弹窗"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </header>

        <div className="max-h-[68vh] overflow-y-auto px-5 py-4">
          {thinking ? (
            <div className="rounded-xl border border-border bg-background p-4">
              <MarkdownBlock
                content={thinking}
                className="prose prose-sm max-w-none break-words prose-headings:tracking-tight prose-p:leading-relaxed prose-pre:whitespace-pre-wrap prose-table:text-xs dark:prose-invert"
              />
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border bg-background px-4 py-8 text-center text-sm text-muted-foreground">
              {row.status === 'running' ? '该 Agent 正在思考，内容生成后会自动更新。' : '当前没有可展示的思考内容。'}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function AgentReportModal({ row, isOpen, onClose }) {
  useEffect(() => {
    if (!isOpen) return undefined;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onEsc = (event) => {
      if (event.key === 'Escape') {
        onClose?.();
      }
    };

    window.addEventListener('keydown', onEsc);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener('keydown', onEsc);
    };
  }, [isOpen, onClose]);

  if (!isOpen || !row) return null;

  const report = String(row.content || '').trim();

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4" role="presentation">
      <button
        type="button"
        aria-label="关闭报告浮窗"
        onClick={onClose}
        className="absolute inset-0 bg-background/75 backdrop-blur-sm"
      />
      <section
        role="dialog"
        aria-modal="true"
        aria-label={`${row.label} 的报告内容`}
        className="relative z-[111] w-full max-w-3xl rounded-2xl border border-border bg-card shadow-2xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div>
            <h3 className="text-base font-semibold text-foreground">{row.label} · Agent 报告</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              状态：{row.statusLabel} · {row.error ? `提示：${row.error}` : row.durationText}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border p-2 text-muted-foreground transition-colors hover:bg-accent/70 hover:text-foreground"
            aria-label="关闭弹窗"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </header>

        <div className="max-h-[68vh] overflow-y-auto px-5 py-4">
          {report ? (
            <div className="rounded-xl border border-border bg-background p-4">
              <MarkdownBlock
                content={report}
                className="prose prose-sm max-w-none break-words prose-headings:tracking-tight prose-p:leading-relaxed prose-pre:whitespace-pre-wrap prose-table:text-xs dark:prose-invert"
              />
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border bg-background px-4 py-8 text-center text-sm text-muted-foreground">
              {row.status === 'running' ? '该 Agent 正在生成报告，内容生成后会自动更新。' : '当前没有可展示的 Agent 报告。'}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function DebateSummary({ exchanges, onOpenExchange }) {
  if (!Array.isArray(exchanges) || exchanges.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无交叉讨论内容。</p>;
  }

  return (
    <div className="space-y-3">
      {exchanges.slice(-4).map((ex, idx) => {
        const markdown = composeDebateMarkdown(ex);
        const hasContent = Boolean(markdown);

        return (
          <article key={`${ex.roundNumber}-${ex.challenger}-${idx}`} className="rounded-xl border border-border bg-background p-3">
            <p className="text-xs text-muted-foreground">
              第 {ex.roundNumber || '--'} 轮 · {displayAgentName(ex.challenger)} {'>'} {displayAgentName(ex.responder)}
            </p>

            <div className="mt-2 max-h-52 overflow-y-auto rounded-lg border border-border bg-card p-3">
              {hasContent ? (
                <MarkdownBlock
                  content={markdown}
                  className="prose prose-sm max-w-none break-words prose-headings:tracking-tight prose-p:leading-relaxed prose-pre:whitespace-pre-wrap prose-table:text-xs dark:prose-invert"
                />
              ) : (
                <p className="text-sm text-muted-foreground">暂无内容</p>
              )}
            </div>

            <div className="mt-2 flex justify-end">
              <button
                type="button"
                onClick={() => onOpenExchange?.(ex)}
                disabled={!hasContent}
                className="h-8 rounded-lg border border-border px-3 text-xs font-medium text-foreground transition-colors hover:bg-accent/70 disabled:cursor-not-allowed disabled:opacity-60"
              >
                浮窗查看全文
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function DebateExchangeModal({ exchange, isOpen, onClose }) {
  useEffect(() => {
    if (!isOpen) return undefined;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onEsc = (event) => {
      if (event.key === 'Escape') {
        onClose?.();
      }
    };

    window.addEventListener('keydown', onEsc);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener('keydown', onEsc);
    };
  }, [isOpen, onClose]);

  if (!isOpen || !exchange) return null;

  const markdown = composeDebateMarkdown(exchange);

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4" role="presentation">
      <button
        type="button"
        aria-label="关闭交叉讨论浮窗"
        onClick={onClose}
        className="absolute inset-0 bg-background/75 backdrop-blur-sm"
      />
      <section
        role="dialog"
        aria-modal="true"
        aria-label="交叉讨论详情"
        className="relative z-[111] w-full max-w-4xl rounded-2xl border border-border bg-card shadow-2xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div>
            <h3 className="text-base font-semibold text-foreground">
              第 {exchange.roundNumber || '--'} 轮 · {displayAgentName(exchange.challenger)} {'>'} {displayAgentName(exchange.responder)}
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">交叉讨论详情（Markdown 渲染）</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border p-2 text-muted-foreground transition-colors hover:bg-accent/70 hover:text-foreground"
            aria-label="关闭弹窗"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </header>

        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">
          {markdown ? (
            <div className="rounded-xl border border-border bg-background p-4">
              <MarkdownBlock
                content={markdown}
                className="prose prose-sm max-w-none break-words prose-headings:tracking-tight prose-p:leading-relaxed prose-pre:whitespace-pre-wrap prose-table:text-xs dark:prose-invert"
              />
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border bg-background px-4 py-8 text-center text-sm text-muted-foreground">
              当前没有可展示的交叉讨论内容。
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

export default function Home() {
  const state = useWorkflowState();
  const actions = useWorkflowActions();
  const { startStream } = useStreamV2();

  const {
    userProfile,
    isGenerating,
    synthesizedReport,
    reportHtmlUrl,
    error,
    toolMetrics,
    demoMetrics,
    reportCharts,
    recovery,
    enableWebsearch,
  } = state;

  const [activeView, setActiveView] = useState('overview');
  const [analysisPrefs, setAnalysisPrefs] = useState(getDefaultAnalysisPreferences());
  const [prefsDraft, setPrefsDraft] = useState(getDefaultAnalysisPreferences());
  const [demoPresetId, setDemoPresetId] = useState(DEFAULT_DEMO_PRESET_ID);
  const [debateRounds, setDebateRounds] = useState(getDefaultAnalysisPreferences().defaultDebateRounds);
  const [profileDraft, setProfileDraft] = useState(DEFAULT_PROFILE_DRAFT);
  const [historySessions, setHistorySessions] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [historyOffset, setHistoryOffset] = useState(0);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [historyStatusFilter, setHistoryStatusFilter] = useState(getDefaultAnalysisPreferences().historyStatusFilter);
  const [loadingSessionId, setLoadingSessionId] = useState('');
  const [thinkingModalAgentKey, setThinkingModalAgentKey] = useState('');
  const [reportModalAgentKey, setReportModalAgentKey] = useState('');
  const [activeDebateExchange, setActiveDebateExchange] = useState(null);

  const resolvedReportHtmlUrl = useMemo(() => {
    if (!reportHtmlUrl) return '';
    return reportHtmlUrl.startsWith('http') ? reportHtmlUrl : `${API_BASE_URL}${reportHtmlUrl}`;
  }, [reportHtmlUrl]);

  const resolvedRoadshowZipUrl = useMemo(() => {
    if (!state.sessionId) return '';
    return `${API_ENDPOINTS.MARKET_INSIGHT_EXPORT}/${state.sessionId}.zip`;
  }, [state.sessionId]);

  const activeDemoPreset = useMemo(() => getDemoPresetById(demoPresetId), [demoPresetId]);

  const sortedDebates = useMemo(() => {
    const rows = Array.isArray(state.debateExchanges) ? state.debateExchanges : [];
    return [...rows].sort((a, b) => (a.roundNumber || 0) - (b.roundNumber || 0));
  }, [state.debateExchanges]);

  const applyAnalysisPrefs = useCallback((nextPrefs) => {
    const normalized = sanitizeAnalysisPreferences(nextPrefs);
    setAnalysisPrefs(normalized);
    saveAnalysisPreferences(normalized);
    return normalized;
  }, []);

  useEffect(() => {
    const loaded = loadAnalysisPreferences();
    setAnalysisPrefs(loaded);
    setPrefsDraft(loaded);
    setDemoPresetId(loaded.defaultDemoPresetId);
    setDebateRounds(loaded.defaultDebateRounds);
    setHistoryStatusFilter(loaded.historyStatusFilter);
  }, []);

  useEffect(() => {
    if (!userProfile) return;
    setProfileDraft(normalizeProfileDraft(userProfile));
  }, [userProfile]);

  const buildRunOptions = useCallback((presetId, overrideDebateRounds = null) => {
    const preset = getDemoPresetById(presetId);
    const rounds = typeof overrideDebateRounds === 'number'
      ? overrideDebateRounds
      : analysisPrefs.defaultDebateRounds;

    return {
      ...preset.request,
      debateRounds: rounds,
      retryMaxAttempts: analysisPrefs.retryMaxAttempts,
      retryBackoffMs: analysisPrefs.retryBackoffMs,
      degradeMode: analysisPrefs.degradeMode,
    };
  }, [analysisPrefs]);

  const runWithProfile = useCallback(async (rawProfile, presetId, overrideRounds = null) => {
    const profile = normalizeProfileDraft(rawProfile);
    actions.clearError();
    actions.setProfile(profile);
    setProfileDraft(profile);
    setActiveView('overview');

    await startStream({
      profile,
      ...buildRunOptions(presetId, overrideRounds),
      enableWebsearch,
    });
  }, [actions, buildRunOptions, enableWebsearch, startStream]);

  const setWebsearchEnabled = useCallback((nextEnabled) => {
    const target = Boolean(nextEnabled);
    const current = Boolean(enableWebsearch);
    if (target !== current) {
      actions.toggleWebsearch();
    }
  }, [actions, enableWebsearch]);

  const handleToggleWebsearch = useCallback(() => {
    if (isGenerating) return;
    setWebsearchEnabled(!enableWebsearch);
  }, [enableWebsearch, isGenerating, setWebsearchEnabled]);

  const handleOnboardingSubmit = useCallback(async (profile) => {
    await runWithProfile(profile, demoPresetId, debateRounds);
  }, [debateRounds, demoPresetId, runWithProfile]);

  const handleStart = useCallback(async () => {
    await runWithProfile(profileDraft, demoPresetId, debateRounds);
  }, [debateRounds, demoPresetId, profileDraft, runWithProfile]);

  const handleRunPreset = useCallback(async (presetId) => {
    const preset = getDemoPresetById(presetId);
    setDemoPresetId(preset.id);
    setDebateRounds(preset.request.debateRounds);
    await runWithProfile(profileDraft, preset.id, preset.request.debateRounds);
  }, [profileDraft, runWithProfile]);

  const applyTaskTemplate = useCallback((templateId) => {
    const template = TASK_TEMPLATES.find((item) => item.id === templateId);
    if (!template) return;
    setProfileDraft(normalizeProfileDraft(template.profile));
  }, []);

  const handleSetDefaultPreset = useCallback((nextPresetId) => {
    const preset = getDemoPresetById(nextPresetId);
    setDemoPresetId(preset.id);
    setDebateRounds(preset.request.debateRounds);

    const normalized = applyAnalysisPrefs({
      ...analysisPrefs,
      defaultDemoPresetId: preset.id,
      defaultDebateRounds: preset.request.debateRounds,
    });
    setPrefsDraft(normalized);
  }, [analysisPrefs, applyAnalysisPrefs]);

  const fetchHistorySessions = useCallback(async ({ append = false, offset = 0 } = {}) => {
    setHistoryLoading(true);
    setHistoryError('');
    try {
      const params = new URLSearchParams({
        limit: String(HISTORY_PAGE_SIZE),
        offset: String(offset),
      });
      if (historyStatusFilter !== 'all') {
        params.set('status', historyStatusFilter);
      }

      const resp = await fetch(`${API_ENDPOINTS.MARKET_INSIGHT_SESSIONS}?${params.toString()}`);
      if (!resp.ok) {
        throw new Error(`历史会话查询失败（${resp.status}）`);
      }

      const data = await resp.json();
      const rows = Array.isArray(data.sessions) ? data.sessions : [];

      setHistorySessions((prev) => (append ? [...prev, ...rows] : rows));
      setHistoryOffset(Number(data.next_offset || (offset + rows.length)));
      setHistoryHasMore(Boolean(data.has_more));
    } catch (e) {
      setHistoryError(e?.message || '历史会话加载失败');
    } finally {
      setHistoryLoading(false);
    }
  }, [historyStatusFilter]);

  useEffect(() => {
    if (activeView !== 'history') return;
    fetchHistorySessions({ append: false, offset: 0 });
  }, [activeView, historyStatusFilter, fetchHistorySessions]);

  const handleHistoryFilterChange = useCallback((nextValue) => {
    const nextFilter = String(nextValue || 'all');
    setHistoryStatusFilter(nextFilter);
    const normalized = applyAnalysisPrefs({
      ...analysisPrefs,
      historyStatusFilter: nextFilter,
    });
    setPrefsDraft(normalized);
  }, [analysisPrefs, applyAnalysisPrefs]);

  const handleLoadSession = useCallback(async (sessionId) => {
    if (!sessionId || loadingSessionId) return;
    setLoadingSessionId(sessionId);
    setHistoryError('');
    try {
      const resp = await fetch(`${API_ENDPOINTS.MARKET_INSIGHT_STATUS}/${sessionId}`);
      if (!resp.ok) {
        throw new Error(`会话状态加载失败（${resp.status}）`);
      }
      const payload = await resp.json();
      if (payload?.status === 'not_found') {
        throw new Error('会话不存在或已被清理');
      }
      actions.hydrateFromStatus(payload);
      actions.clearError();
      setActiveView('overview');
    } catch (e) {
      setHistoryError(e?.message || '加载会话失败');
    } finally {
      setLoadingSessionId('');
    }
  }, [actions, loadingSessionId]);

  const handleSavePreferences = useCallback(() => {
    const normalized = applyAnalysisPrefs(prefsDraft);
    setPrefsDraft(normalized);
    setDemoPresetId(normalized.defaultDemoPresetId);
    setDebateRounds(normalized.defaultDebateRounds);
    setHistoryStatusFilter(normalized.historyStatusFilter);
    setActiveView('overview');
  }, [applyAnalysisPrefs, prefsDraft]);

  const handleResetPreferences = useCallback(() => {
    const defaults = getDefaultAnalysisPreferences();
    const normalized = applyAnalysisPrefs(defaults);
    setPrefsDraft(normalized);
    setDemoPresetId(normalized.defaultDemoPresetId);
    setDebateRounds(normalized.defaultDebateRounds);
    setHistoryStatusFilter(normalized.historyStatusFilter);
  }, [applyAnalysisPrefs]);

  const setProgressViewMode = useCallback((mode) => {
    const normalized = applyAnalysisPrefs({
      ...analysisPrefs,
      progressViewMode: mode,
    });
    setPrefsDraft(normalized);
  }, [analysisPrefs, applyAnalysisPrefs]);

  const handleExport = useCallback(() => {
    if (resolvedRoadshowZipUrl) {
      window.open(resolvedRoadshowZipUrl, '_blank');
    }
  }, [resolvedRoadshowZipUrl]);

  const handlePreview = useCallback(() => {
    if (resolvedReportHtmlUrl) {
      window.open(resolvedReportHtmlUrl, '_blank');
    }
  }, [resolvedReportHtmlUrl]);

  const openThinkingModal = useCallback((agentKey) => {
    if (!agentKey) return;
    setActiveDebateExchange(null);
    setReportModalAgentKey('');
    setThinkingModalAgentKey(String(agentKey));
  }, []);

  const closeThinkingModal = useCallback(() => {
    setThinkingModalAgentKey('');
  }, []);

  const openReportModal = useCallback((agentKey) => {
    if (!agentKey) return;
    setActiveDebateExchange(null);
    setThinkingModalAgentKey('');
    setReportModalAgentKey(String(agentKey));
  }, []);

  const closeReportModal = useCallback(() => {
    setReportModalAgentKey('');
  }, []);

  const openDebateExchangeModal = useCallback((exchange) => {
    if (!exchange) return;
    setThinkingModalAgentKey('');
    setReportModalAgentKey('');
    setActiveDebateExchange(exchange);
  }, []);

  const closeDebateExchangeModal = useCallback(() => {
    setActiveDebateExchange(null);
  }, []);

  const progressRows = useMemo(() => AGENT_PIPELINE.map((agentKey) => {
    const row = state.agentResults?.[agentKey] || {};
    const status = String(row.status || 'pending').toLowerCase();
    const toneMap = {
      completed: 'border-emerald-500/35 text-emerald-600 dark:text-emerald-400',
      running: 'border-gemini-blue/35 text-gemini-blue',
      failed: 'border-red-500/35 text-red-600 dark:text-red-400',
      degraded: 'border-amber-500/35 text-amber-600 dark:text-amber-400',
      skipped: 'border-slate-500/35 text-slate-600 dark:text-slate-300',
      pending: 'border-border text-muted-foreground',
    };
    const labelMap = {
      completed: '已完成',
      running: '进行中',
      failed: '失败',
      degraded: '降级完成',
      skipped: '已跳过',
      pending: '等待中',
    };
    return {
      key: agentKey,
      label: displayAgentName(agentKey),
      status,
      statusLabel: labelMap[status] || '等待中',
      tone: toneMap[status] || toneMap.pending,
      error: row.error,
      thinking: row.thinking || '',
      content: row.content || '',
      durationText: row.durationMs ? `耗时 ${formatDuration(row.durationMs)}` : '等待执行',
    };
  }), [state.agentResults]);

  const activeThinkingRow = useMemo(
    () => progressRows.find((row) => row.key === thinkingModalAgentKey) || null,
    [progressRows, thinkingModalAgentKey]
  );

  const activeReportRow = useMemo(
    () => progressRows.find((row) => row.key === reportModalAgentKey) || null,
    [progressRows, reportModalAgentKey]
  );

  useEffect(() => {
    if (activeView !== 'overview') {
      setThinkingModalAgentKey('');
      setReportModalAgentKey('');
      setActiveDebateExchange(null);
    }
  }, [activeView]);

  const progressSummary = useMemo(() => {
    const counters = { completed: 0, failed: 0, running: 0, pending: 0 };
    progressRows.forEach((row) => {
      if (row.statusLabel === '已完成' || row.statusLabel === '降级完成' || row.statusLabel === '已跳过') {
        counters.completed += 1;
      } else if (row.statusLabel === '失败') {
        counters.failed += 1;
      } else if (row.statusLabel === '进行中') {
        counters.running += 1;
      } else {
        counters.pending += 1;
      }
    });
    return counters;
  }, [progressRows]);

  const reportConclusions = useMemo(() => extractTopConclusions(synthesizedReport, 3), [synthesizedReport]);
  const actionSuggestions = useMemo(
    () => buildActionSuggestions(demoMetrics, recovery, toolMetrics),
    [demoMetrics, recovery, toolMetrics]
  );

  const recoveryMessage = useMemo(() => {
    if (!recovery || recovery.mode === 'idle') {
      return '网络波动时会自动恢复，无需手动刷新。';
    }
    if (recovery.mode === 'recovering') {
      return `正在恢复：${recoveryReasonLabel(recovery.reason)}，已尝试 ${recovery.attempts || 0} 次。`;
    }
    if (recovery.mode === 'recovered') {
      return `已恢复：${recoveryReasonLabel(recovery.reason)}。`;
    }
    return `恢复超时：${recoveryReasonLabel(recovery.reason)}。`;
  }, [recovery]);

  const startButtonClass = synthesizedReport
    ? 'h-11 rounded-xl border border-border px-4 text-sm font-semibold text-foreground transition-colors hover:bg-accent/70'
    : 'h-11 rounded-xl bg-foreground px-4 text-sm font-semibold text-background transition-transform duration-200 hover:scale-[1.01] active:scale-[0.99]';

  if (!userProfile) {
    return (
      <main id="main-content" className="min-h-screen bg-background px-4 py-8 md:px-8 md:py-12">
        <div className="mx-auto grid w-full max-w-5xl gap-6 md:grid-cols-[minmax(0,1fr)_360px]">
          <section className="surface-card p-5 md:p-8">
            <div className="mb-6">
              <p className="inline-flex items-center gap-2 rounded-full border border-gemini-blue/30 bg-gemini-blue/10 px-3 py-1 text-xs font-medium text-gemini-blue">
                <Sparkles size={14} aria-hidden="true" />
                一屏完成首次分析
              </p>
              <h1 className="mt-4 text-3xl font-semibold tracking-tight text-foreground md:text-4xl" style={{ textWrap: 'balance' }}>
                输入你的业务目标，系统会自动给出行动建议
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                你只需要填写市场、品类和价格区间。分析完成后会直接给你关键结论、关键图表和导出报告入口。
              </p>
            </div>

            <div className="mb-5 space-y-3">
              <div>
                <p className="text-xs font-medium text-muted-foreground">选择分析速度（评委模式入口）</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {DEMO_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => {
                        setDemoPresetId(preset.id);
                        setDebateRounds(preset.request.debateRounds);
                      }}
                      className={`chip-button ${demoPresetId === preset.id ? 'border-gemini-blue/45 bg-gemini-blue/10 text-gemini-blue' : ''}`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <p className="text-xs font-medium text-muted-foreground">常见任务模板</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {TASK_TEMPLATES.map((template) => (
                    <button
                      key={template.id}
                      type="button"
                      onClick={() => applyTaskTemplate(template.id)}
                      className="chip-button"
                    >
                      {template.label}
                    </button>
                  ))}
                </div>
              </div>

              <WebsearchToggle
                enabled={Boolean(enableWebsearch)}
                disabled={isGenerating}
                onToggle={handleToggleWebsearch}
              />
            </div>

            <ProfileForm
              value={profileDraft}
              onChange={(next) => setProfileDraft(normalizeProfileDraft(next))}
              onFormSubmit={handleOnboardingSubmit}
              isLoading={isGenerating}
              submitLabel={`开始分析（${activeDemoPreset.label}）`}
            />
          </section>

          <aside className="surface-card p-5 md:p-6">
            <h2 className="text-base font-semibold">你将得到什么</h2>
            <ul className="mt-4 space-y-3 text-sm text-muted-foreground">
              <li className="flex items-start gap-2">
                <CheckCircle2 size={16} className="mt-0.5 text-emerald-500" aria-hidden="true" />
                关键结论 3 条，适合快速汇报
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 size={16} className="mt-0.5 text-emerald-500" aria-hidden="true" />
                风险提醒 + 优先级行动建议
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 size={16} className="mt-0.5 text-emerald-500" aria-hidden="true" />
                关键图表和完整报告预览
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 size={16} className="mt-0.5 text-emerald-500" aria-hidden="true" />
                先预览再导出完整报告
              </li>
            </ul>
          </aside>
        </div>
      </main>
    );
  }

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <ModernSidebar
        onReset={() => {
          actions.resetSession();
          setProfileDraft(DEFAULT_PROFILE_DRAFT);
          setActiveView('overview');
        }}
        isGenerating={isGenerating}
        activeView={activeView}
        onNavigate={setActiveView}
        historyCount={historySessions.length}
      />

      <main id="main-content" className="flex min-w-0 flex-1 flex-col">
        <ModernHeader isGenerating={isGenerating} recoveryMode={recovery?.mode} />

        <div className="mx-auto w-full max-w-6xl flex-1 space-y-4 px-4 py-4 md:px-6 md:py-6">
          {activeView === 'overview' && (
            <>
              <section className="surface-card p-5 md:p-6">
                <SectionTitle
                  icon={LayoutGrid}
                  title="开始新一轮分析"
                  subtitle="先确认目标和分析速度，再一键开始。"
                />

                <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
                  <div className="rounded-2xl border border-border bg-background p-4">
                    <h3 className="text-sm font-semibold">当前目标信息</h3>
                    <dl className="mt-3 grid grid-cols-1 gap-2 text-sm text-muted-foreground md:grid-cols-2">
                      <div>
                        <dt className="text-xs">目标市场</dt>
                        <dd className="text-foreground">{profileDraft.target_market}</dd>
                      </div>
                      <div>
                        <dt className="text-xs">核心品类</dt>
                        <dd className="text-foreground">{profileDraft.supply_chain}</dd>
                      </div>
                      <div>
                        <dt className="text-xs">卖家类型</dt>
                        <dd className="text-foreground">{profileDraft.seller_type}</dd>
                      </div>
                      <div>
                        <dt className="text-xs">价格区间</dt>
                        <dd className="text-foreground numeric">
                          ${profileDraft.min_price} - ${profileDraft.max_price}
                        </dd>
                      </div>
                    </dl>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {TASK_TEMPLATES.map((template) => (
                        <button
                          key={template.id}
                          type="button"
                          className="chip-button"
                          onClick={() => applyTaskTemplate(template.id)}
                        >
                          {template.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border bg-background p-4">
                    <div className="space-y-3">
                      <LabeledSelect
                        id="quick-preset"
                        label="分析速度"
                        value={demoPresetId}
                        onChange={(nextValue) => {
                          const preset = getDemoPresetById(nextValue);
                          setDemoPresetId(preset.id);
                          setDebateRounds(preset.request.debateRounds);
                        }}
                        options={DEMO_PRESETS.map((preset) => ({
                          value: preset.id,
                          label: `${preset.label}（${preset.targetDuration}）`,
                        }))}
                        disabled={isGenerating}
                      />

                      <LabeledSelect
                        id="quick-rounds"
                        label="复核轮次"
                        value={String(debateRounds)}
                        onChange={(nextValue) => setDebateRounds(Number(nextValue))}
                        options={[
                          { value: '0', label: '0 轮（更快）' },
                          { value: '1', label: '1 轮（平衡）' },
                          { value: '2', label: '2 轮（更稳）' },
                        ]}
                        disabled={isGenerating}
                      />

                      <WebsearchToggle
                        enabled={Boolean(enableWebsearch)}
                        disabled={isGenerating}
                        onToggle={handleToggleWebsearch}
                      />
                    </div>

                    <div className="mt-4 flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        disabled={isGenerating}
                        onClick={handleStart}
                        className={startButtonClass}
                      >
                        {isGenerating ? '分析进行中…' : synthesizedReport ? '重新分析' : '开始分析'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleSetDefaultPreset(demoPresetId)}
                        disabled={isGenerating}
                        className="h-11 rounded-xl border border-border px-4 text-sm text-muted-foreground transition-colors hover:bg-accent/70 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        设为默认速度
                      </button>
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">当前速度：{activeDemoPreset.description} · 联网搜索：{enableWebsearch ? '已开启' : '已关闭'}</p>
                  </div>
                </div>
              </section>

              <section className="surface-card p-5 md:p-6">
                <SectionTitle
                  icon={Activity}
                  title="分析进度"
                  subtitle="默认展示简版进度，你可以切换到专业视图。"
                />

                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                    <div className="rounded-xl border border-border bg-background px-3 py-2">
                      <p className="text-xs text-muted-foreground">已完成</p>
                      <p className="numeric text-lg font-semibold">{progressSummary.completed}</p>
                    </div>
                    <div className="rounded-xl border border-border bg-background px-3 py-2">
                      <p className="text-xs text-muted-foreground">进行中</p>
                      <p className="numeric text-lg font-semibold">{progressSummary.running}</p>
                    </div>
                    <div className="rounded-xl border border-border bg-background px-3 py-2">
                      <p className="text-xs text-muted-foreground">等待中</p>
                      <p className="numeric text-lg font-semibold">{progressSummary.pending}</p>
                    </div>
                    <div className="rounded-xl border border-border bg-background px-3 py-2">
                      <p className="text-xs text-muted-foreground">失败</p>
                      <p className="numeric text-lg font-semibold">{progressSummary.failed}</p>
                    </div>
                  </div>

                  <div className="inline-flex rounded-xl border border-border bg-background p-1">
                    <button
                      type="button"
                      onClick={() => setProgressViewMode('simple')}
                      className={`rounded-lg px-3 py-1.5 text-xs font-medium ${analysisPrefs.progressViewMode === 'simple' ? 'bg-gemini-blue/15 text-gemini-blue' : 'text-muted-foreground hover:text-foreground'}`}
                    >
                      简版
                    </button>
                    <button
                      type="button"
                      onClick={() => setProgressViewMode('professional')}
                      className={`rounded-lg px-3 py-1.5 text-xs font-medium ${analysisPrefs.progressViewMode === 'professional' ? 'bg-gemini-blue/15 text-gemini-blue' : 'text-muted-foreground hover:text-foreground'}`}
                    >
                      专业版
                    </button>
                  </div>
                </div>

                {analysisPrefs.progressViewMode === 'professional' ? (
                  <ProfessionalProgress
                    rows={progressRows}
                    onOpenThinking={openThinkingModal}
                    onOpenReport={openReportModal}
                  />
                ) : (
                  <ProgressStepList rows={progressRows} />
                )}

                <div className={`mt-4 rounded-xl border px-3 py-2 text-sm ${recovery?.mode === 'timeout' ? 'border-red-500/40 bg-red-500/5 text-red-600 dark:text-red-400' : recovery?.mode === 'recovering' ? 'border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-300' : 'border-border bg-background text-muted-foreground'}`}>
                  <div className="flex items-center gap-2">
                    <ShieldAlert size={14} aria-hidden="true" />
                    <span>{recoveryMessage}</span>
                  </div>
                  {recovery?.mode !== 'idle' && (
                    <p className="mt-1 text-xs">原因：{recoveryReasonLabel(recovery.reason)} · 已轮询 {recovery.attempts || 0} 次</p>
                  )}
                </div>

                {error && (
                  <div className="mt-4 rounded-xl border border-red-500/35 bg-red-500/5 px-3 py-2 text-sm text-red-600 dark:text-red-400" role="alert">
                    {error}
                  </div>
                )}
              </section>

              <section className="surface-card p-5 md:p-6">
                <SectionTitle
                  icon={FileText}
                  title="分析结果"
                  subtitle="先看建议，再看结论和图表。"
                />

                {!synthesizedReport && !isGenerating && (
                  <div className="rounded-2xl border border-dashed border-border bg-background px-4 py-10 text-center text-sm text-muted-foreground">
                    结果会显示在这里。先点击上方“开始分析”。
                  </div>
                )}

                {isGenerating && !synthesizedReport && (
                  <div className="rounded-2xl border border-border bg-background px-4 py-8" aria-live="polite">
                    <p className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                      <Activity size={14} className="animate-pulse" aria-hidden="true" />
                      正在生成结果，请稍候…
                    </p>
                  </div>
                )}

                {synthesizedReport && (
                  <div className="space-y-5">
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                      {actionSuggestions.map((item) => (
                        <article key={item.title} className="rounded-xl border border-border bg-background p-3">
                          <h3 className="text-sm font-semibold text-foreground">{item.title}</h3>
                          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{item.content}</p>
                        </article>
                      ))}
                    </div>

                    <article className="rounded-xl border border-border bg-background p-4">
                      <h3 className="mb-2 text-sm font-semibold">关键结论 3 条</h3>
                      {reportConclusions.length > 0 ? (
                        <ol className="list-decimal space-y-1 pl-5 text-sm text-foreground">
                          {reportConclusions.map((item, idx) => (
                            <li key={`${item}-${idx}`} className="leading-relaxed">{item}</li>
                          ))}
                        </ol>
                      ) : (
                        <p className="text-sm text-muted-foreground">还在整理结论，请查看完整报告。</p>
                      )}
                    </article>

                    <article>
                      <h3 className="mb-2 text-sm font-semibold">关键图表</h3>
                      <VegaLiteCharts reportCharts={reportCharts} maxCharts={2} />
                    </article>

                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={handlePreview}
                        disabled={!resolvedReportHtmlUrl}
                        className="inline-flex h-11 items-center rounded-xl border border-border px-4 text-sm font-semibold text-foreground transition-colors hover:bg-accent/70 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <Eye size={16} aria-hidden="true" className="mr-2" />
                        先预览报告
                      </button>
                      <button
                        type="button"
                        onClick={handleExport}
                        disabled={!resolvedRoadshowZipUrl}
                        className="inline-flex h-11 items-center rounded-xl bg-foreground px-4 text-sm font-semibold text-background transition-transform duration-200 hover:scale-[1.01] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <Download size={16} aria-hidden="true" className="mr-2" />
                        导出完整报告
                      </button>
                    </div>
                    <p className="text-xs text-muted-foreground">建议先预览，再导出完整报告。</p>

                    <details className="rounded-xl border border-border bg-background p-4">
                      <summary className="cursor-pointer text-sm font-medium text-foreground">查看完整正文</summary>
                      <MarkdownBlock
                        content={synthesizedReport}
                        className="prose prose-sm mt-4 max-w-none prose-headings:tracking-tight prose-p:leading-relaxed dark:prose-invert"
                      />
                    </details>
                  </div>
                )}
              </section>

              <details className="surface-card p-5 md:p-6">
                <summary className="cursor-pointer text-sm font-semibold text-foreground">查看专业详情（过程与指标）</summary>

                <div className="mt-4 space-y-5">
                  <section>
                    <SectionTitle
                      icon={ListChecks}
                      title="交叉讨论摘要"
                      subtitle="保留核心观点，不影响首屏阅读。"
                    />
                    <DebateSummary
                      exchanges={sortedDebates}
                      onOpenExchange={openDebateExchangeModal}
                    />
                  </section>

                  <section>
                    <SectionTitle
                      icon={BarChart3}
                      title="过程指标"
                      subtitle="用于排查稳定性和迭代效率。"
                    />

                    {demoMetrics ? (
                      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                        <div className="rounded-xl border border-border bg-background px-3 py-2">
                          <p className="text-xs text-muted-foreground">总耗时</p>
                          <p className="numeric text-lg font-semibold">{formatDuration(demoMetrics.total_duration_ms)}</p>
                        </div>
                        <div className="rounded-xl border border-border bg-background px-3 py-2">
                          <p className="text-xs text-muted-foreground">稳定性</p>
                          <p className="numeric text-lg font-semibold">{Number(demoMetrics.stability_score || 0).toFixed(1)}</p>
                        </div>
                        <div className="rounded-xl border border-border bg-background px-3 py-2">
                          <p className="text-xs text-muted-foreground">证据覆盖</p>
                          <p className="numeric text-lg font-semibold">{((demoMetrics.evidence_coverage_rate || 0) * 100).toFixed(1)}%</p>
                        </div>
                        <div className="rounded-xl border border-border bg-background px-3 py-2">
                          <p className="text-xs text-muted-foreground">降级次数</p>
                          <p className="numeric text-lg font-semibold">{demoMetrics.degrade_count || 0}</p>
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">暂无过程指标。</p>
                    )}
                  </section>
                </div>
              </details>
            </>
          )}

          {activeView === 'history' && (
            <section className="surface-card p-5 md:p-6">
              <SectionTitle icon={History} title="历史会话" subtitle="继续上次分析，减少重复操作。" />

              <div className="mb-4 flex flex-wrap items-center gap-2">
                <LabeledSelect
                  id="history-filter"
                  label="筛选状态"
                  value={historyStatusFilter}
                  onChange={handleHistoryFilterChange}
                  disabled={historyLoading}
                  options={[
                    { value: 'all', label: '全部状态' },
                    { value: 'running', label: '进行中' },
                    { value: 'completed', label: '已完成' },
                    { value: 'failed', label: '失败' },
                    { value: 'cancelled', label: '已取消' },
                  ]}
                />
                <button
                  type="button"
                  onClick={() => fetchHistorySessions({ append: false, offset: 0 })}
                  disabled={historyLoading}
                  className="mt-6 h-10 rounded-xl border border-border px-4 text-sm text-muted-foreground transition-colors hover:bg-accent/70 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
                >
                  刷新
                </button>
              </div>

              {historyError && (
                <div className="mb-4 rounded-xl border border-red-500/35 bg-red-500/5 px-3 py-2 text-sm text-red-600 dark:text-red-400" role="alert">
                  {historyError}
                </div>
              )}

              {historySessions.length === 0 && !historyLoading ? (
                <p className="rounded-xl border border-dashed border-border bg-background px-4 py-10 text-center text-sm text-muted-foreground">
                  还没有历史会话，先完成一次分析。
                </p>
              ) : (
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {historySessions.map((item) => {
                    const profile = item?.profile || {};
                    const isCurrent = item?.id === state.sessionId;
                    return (
                      <article key={item.id} className="rounded-xl border border-border bg-background p-4">
                        <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
                          <span>{formatDateTime(item.started_at || item.created_at)}</span>
                          <span className="status-pill">{sessionStatusLabel(item.status)}</span>
                        </div>
                        <h3 className="text-sm font-semibold text-foreground">
                          {profile.target_market || '未知市场'} · {profile.supply_chain || '未知品类'}
                        </h3>
                        <p className="mt-1 text-xs text-muted-foreground">卖家类型：{profile.seller_type || '未填写'}</p>
                        <p className="mt-3 line-clamp-2 text-xs text-muted-foreground">
                          {item.report_preview ? String(item.report_preview).replace(/^#+\s*/, '') : '暂无摘要'}
                        </p>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleLoadSession(item.id)}
                            disabled={Boolean(loadingSessionId) || historyLoading}
                            className="h-10 rounded-xl bg-foreground px-3 text-sm font-medium text-background disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {loadingSessionId === item.id ? '加载中…' : isCurrent ? '当前会话' : '继续分析'}
                          </button>
                          {item.report_html_url && (
                            <button
                              type="button"
                              onClick={() => {
                                const url = item.report_html_url.startsWith('http')
                                  ? item.report_html_url
                                  : `${API_BASE_URL}${item.report_html_url}`;
                                window.open(url, '_blank');
                              }}
                              className="h-10 rounded-xl border border-border px-3 text-sm text-foreground transition-colors hover:bg-accent/70"
                            >
                              查看预览
                            </button>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}

              {historyHasMore && (
                <div className="mt-4 flex justify-center">
                  <button
                    type="button"
                    onClick={() => fetchHistorySessions({ append: true, offset: historyOffset })}
                    disabled={historyLoading}
                    className="h-10 rounded-xl border border-border px-4 text-sm text-muted-foreground transition-colors hover:bg-accent/70 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {historyLoading ? '加载中…' : '加载更多'}
                  </button>
                </div>
              )}
            </section>
          )}

          {activeView === 'preferences' && (
            <section className="surface-card p-5 md:p-6">
              <SectionTitle icon={Settings2} title="偏好设置" subtitle="保存后会应用到下一次分析。" />

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                <LabeledSelect
                  id="pref-default-preset"
                  label="默认分析速度"
                  value={prefsDraft.defaultDemoPresetId}
                  onChange={(val) => setPrefsDraft((prev) => ({ ...prev, defaultDemoPresetId: String(val) }))}
                  options={DEMO_PRESETS.map((preset) => ({ value: preset.id, label: preset.label }))}
                />

                <LabeledSelect
                  id="pref-default-rounds"
                  label="默认复核轮次"
                  value={String(prefsDraft.defaultDebateRounds)}
                  onChange={(val) => setPrefsDraft((prev) => ({ ...prev, defaultDebateRounds: Number(val) }))}
                  options={[
                    { value: '0', label: '0 轮' },
                    { value: '1', label: '1 轮' },
                    { value: '2', label: '2 轮' },
                  ]}
                />

                <LabeledSelect
                  id="pref-retry-attempts"
                  label="重试次数"
                  value={String(prefsDraft.retryMaxAttempts)}
                  onChange={(val) => setPrefsDraft((prev) => ({ ...prev, retryMaxAttempts: Number(val) }))}
                  options={[
                    { value: '1', label: '1 次' },
                    { value: '2', label: '2 次' },
                    { value: '3', label: '3 次' },
                    { value: '4', label: '4 次' },
                  ]}
                />

                <LabeledSelect
                  id="pref-retry-backoff"
                  label="重试间隔"
                  value={String(prefsDraft.retryBackoffMs)}
                  onChange={(val) => setPrefsDraft((prev) => ({ ...prev, retryBackoffMs: Number(val) }))}
                  options={[
                    { value: '100', label: '100ms' },
                    { value: '300', label: '300ms' },
                    { value: '500', label: '500ms' },
                    { value: '1000', label: '1000ms' },
                  ]}
                />

                <LabeledSelect
                  id="pref-degrade-mode"
                  label="异常处理策略"
                  value={prefsDraft.degradeMode}
                  onChange={(val) => setPrefsDraft((prev) => ({ ...prev, degradeMode: String(val) }))}
                  options={[
                    { value: 'partial', label: '保留可用结果（推荐）' },
                    { value: 'skip', label: '跳过异常步骤' },
                    { value: 'fail', label: '遇错即终止' },
                  ]}
                />

                <LabeledSelect
                  id="pref-history-filter"
                  label="历史默认筛选"
                  value={prefsDraft.historyStatusFilter}
                  onChange={(val) => setPrefsDraft((prev) => ({ ...prev, historyStatusFilter: String(val) }))}
                  options={[
                    { value: 'all', label: '全部状态' },
                    { value: 'running', label: '进行中' },
                    { value: 'completed', label: '已完成' },
                    { value: 'failed', label: '失败' },
                    { value: 'cancelled', label: '已取消' },
                  ]}
                />

                <LabeledSelect
                  id="pref-progress-mode"
                  label="进度展示模式"
                  value={prefsDraft.progressViewMode || 'simple'}
                  onChange={(val) => setPrefsDraft((prev) => ({ ...prev, progressViewMode: String(val) }))}
                  options={[
                    { value: 'simple', label: '简版（默认）' },
                    { value: 'professional', label: '专业版' },
                  ]}
                />
              </div>

              <div className="mt-5 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={handleSavePreferences}
                  className="h-11 rounded-xl bg-foreground px-4 text-sm font-semibold text-background"
                >
                  保存设置
                </button>
                <button
                  type="button"
                  onClick={handleResetPreferences}
                  className="h-11 rounded-xl border border-border px-4 text-sm font-semibold text-foreground transition-colors hover:bg-accent/70"
                >
                  恢复默认
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setPrefsDraft(analysisPrefs);
                    setActiveView('overview');
                  }}
                  className="h-11 rounded-xl border border-border px-4 text-sm text-muted-foreground transition-colors hover:bg-accent/70 hover:text-foreground"
                >
                  返回首页
                </button>
              </div>
            </section>
          )}
        </div>

        <AgentThinkingModal
          row={activeThinkingRow}
          isOpen={Boolean(activeThinkingRow)}
          onClose={closeThinkingModal}
        />

        <AgentReportModal
          row={activeReportRow}
          isOpen={Boolean(activeReportRow)}
          onClose={closeReportModal}
        />

        <DebateExchangeModal
          exchange={activeDebateExchange}
          isOpen={Boolean(activeDebateExchange)}
          onClose={closeDebateExchangeModal}
        />

        <footer className="border-t border-border bg-background/80 px-4 py-3 text-xs text-muted-foreground md:px-6">
          <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1">
              <Clock3 size={12} aria-hidden="true" />
              最近更新时间：{formatDateTime(new Date().toISOString())}
            </span>
            <span className="inline-flex items-center gap-1">
              <ChevronRight size={12} aria-hidden="true" />
              关键入口：首页 / 历史会话 / 偏好设置
            </span>
          </div>
        </footer>
      </main>
    </div>
  );
}
