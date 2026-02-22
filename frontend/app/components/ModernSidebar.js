'use client';

import { useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  History,
  LayoutDashboard,
  RotateCcw,
  Settings2,
} from 'lucide-react';

const MENU_ITEMS = [
  { key: 'overview', icon: LayoutDashboard, label: '首页' },
  { key: 'history', icon: History, label: '历史会话' },
  { key: 'preferences', icon: Settings2, label: '偏好设置' },
];

export default function ModernSidebar({
  onReset,
  isGenerating,
  activeView = 'overview',
  onNavigate,
  historyCount = 0,
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <aside
      className={`sticky top-0 z-30 flex h-screen flex-col border-r border-border bg-background/90 backdrop-blur-sm transition-[width] duration-200 ${isExpanded ? 'w-56' : 'w-[76px]'}`}
      aria-label="侧边导航"
    >
      <div className="flex items-center justify-between px-3 py-4">
        <button
          type="button"
          onClick={() => onNavigate?.('overview')}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-card text-sm font-semibold text-foreground"
          aria-label="回到首页"
        >
          W
        </button>
        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-card text-muted-foreground transition-colors hover:text-foreground"
          aria-label={isExpanded ? '收起侧边栏' : '展开侧边栏'}
        >
          {isExpanded ? <ChevronLeft size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
        </button>
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-2" aria-label="主导航">
        {MENU_ITEMS.map((item) => {
          const isActive = activeView === item.key;
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => onNavigate?.(item.key)}
              className={`group flex h-11 items-center rounded-xl px-2.5 text-sm transition-colors ${isActive ? 'bg-gemini-blue/12 text-gemini-blue' : 'text-muted-foreground hover:bg-accent/70 hover:text-foreground'}`}
              aria-current={isActive ? 'page' : undefined}
              aria-label={item.label}
            >
              <Icon size={18} aria-hidden="true" className="shrink-0" />
              {isExpanded && (
                <span className="ml-3 flex flex-1 items-center justify-between text-left">
                  <span>{item.label}</span>
                  {item.key === 'history' && historyCount > 0 && (
                    <span className="rounded-full border border-border bg-card px-2 py-0.5 text-[11px] text-muted-foreground numeric">
                      {historyCount}
                    </span>
                  )}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="px-2 pb-4">
        <button
          type="button"
          onClick={onReset}
          disabled={isGenerating}
          className="flex h-11 w-full items-center justify-center rounded-xl border border-border bg-card text-sm font-medium text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="开始新的分析"
        >
          <RotateCcw size={16} aria-hidden="true" />
          {isExpanded && <span className="ml-2">重新开始</span>}
        </button>
      </div>
    </aside>
  );
}
