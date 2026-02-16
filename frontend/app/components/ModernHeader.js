'use client';

import ThemeToggle from './ThemeToggle';
import { motion } from 'framer-motion';
import { Share2, Download, Zap } from 'lucide-react';

export default function ModernHeader({ isGenerating, onDownload }) {
  return (
    <header className="sticky top-0 z-10 w-full glass border-b border-border px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-semibold uppercase tracking-wider">
          <Zap size={12} className="fill-current" />
          系统在线
        </div>
        {isGenerating && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center gap-2 text-sm text-muted-foreground"
          >
            <div className="w-1.5 h-1.5 rounded-full bg-gemini-blue animate-pulse" />
            正在编排多 Agent 协作...
          </motion.div>
        )}
      </div>

      <div className="flex items-center gap-3">
        {onDownload && (
          <button 
            onClick={onDownload}
            className="p-2 rounded-xl hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
            title="下载报告"
          >
            <Download size={20} />
          </button>
        )}
        <button className="p-2 rounded-xl hover:bg-accent transition-colors text-muted-foreground hover:text-foreground">
          <Share2 size={20} />
        </button>
        <div className="h-6 w-[1px] bg-border mx-1" />
        <ThemeToggle />
      </div>
    </header>
  );
}
