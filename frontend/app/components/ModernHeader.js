'use client';

import { Activity, Wifi } from 'lucide-react';
import ThemeToggle from './ThemeToggle';

export default function ModernHeader({ isGenerating, recoveryMode = 'idle' }) {
  const isRecovering = recoveryMode === 'recovering';
  const isTimeout = recoveryMode === 'timeout';

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-background/85 px-4 py-3 backdrop-blur-sm md:px-6">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`status-pill ${isTimeout ? 'border-red-500/40 text-red-500' : isRecovering ? 'border-amber-500/40 text-amber-600 dark:text-amber-400' : 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400'}`}>
            <Wifi size={12} aria-hidden="true" />
            {isTimeout ? '连接波动' : isRecovering ? '自动恢复中' : '系统在线'}
          </span>
          {isGenerating && (
            <span className="status-pill" aria-live="polite">
              <Activity size={12} aria-hidden="true" className="animate-pulse" />
              正在分析…
            </span>
          )}
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}
