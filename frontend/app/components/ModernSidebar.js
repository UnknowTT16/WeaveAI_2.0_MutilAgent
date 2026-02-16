'use client';

import { motion } from 'framer-motion';
import { 
  LayoutDashboard, 
  Settings2, 
  History, 
  RotateCcw, 
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  Search,
  Users
} from 'lucide-react';
import { useState } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export default function ModernSidebar({ profile, onReset, isGenerating }) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const menuItems = [
    { icon: LayoutDashboard, label: '概览', active: true },
    { icon: History, label: '历史会话', active: false },
    { icon: Settings2, label: '分析偏好', active: false },
  ];

  return (
    <motion.aside
      initial={false}
      animate={{ width: isCollapsed ? 80 : 280 }}
      className="relative flex flex-col border-r border-border bg-background transition-all duration-300 ease-in-out z-20"
    >
      {/* 折叠按钮 */}
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="absolute -right-3 top-10 w-6 h-6 rounded-full bg-background border border-border flex items-center justify-center hover:scale-110 active:scale-95 transition-transform z-30 shadow-sm"
      >
        {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>

      {/* Logo 区 */}
      <div className="p-6 mb-4 flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-gemini-blue via-gemini-purple to-gemini-red flex items-center justify-center shrink-0 shadow-lg shadow-gemini-blue/20">
          <span className="text-white font-bold text-lg italic">W</span>
        </div>
        {!isCollapsed && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="font-bold text-xl tracking-tight"
          >
            Weave<span className="text-gemini-purple italic">AI</span>
          </motion.span>
        )}
      </div>

      {/* 导航菜单 */}
      <nav className="flex-grow px-4 space-y-2">
        {menuItems.map((item, idx) => (
          <div
            key={idx}
            className={cn(
              "flex items-center gap-3 p-3 rounded-xl transition-all cursor-pointer group",
              item.active 
                ? "bg-accent text-accent-foreground shadow-sm" 
                : "hover:bg-accent/50 text-muted-foreground hover:text-foreground"
            )}
          >
            <item.icon size={20} className={cn(item.active ? "text-inherit" : "group-hover:text-gemini-purple transition-colors")} />
            {!isCollapsed && (
              <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="font-medium text-sm">
                {item.label}
              </motion.span>
            )}
          </div>
        ))}
      </nav>

      {/* 画像摘要 & 重置 */}
      {profile && (
        <div className="p-4 border-t border-border mt-auto">
          {!isCollapsed && (
            <div className="mb-4 space-y-3">
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-2">当前战略档案</div>
              <div className="bg-accent/30 rounded-2xl p-4 space-y-3 border border-border/50">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Search size={14} className="text-gemini-blue" />
                  <span className="truncate">{profile.target_market} · {profile.supply_chain}</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground px-0.5">
                  <Users size={14} />
                  <span>{profile.seller_type}</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground px-0.5">
                  <ShieldCheck size={14} />
                  <span>${profile.min_price} - ${profile.max_price}</span>
                </div>
              </div>
            </div>
          )}
          
          <button
            onClick={onReset}
            disabled={isGenerating}
            className={cn(
              "w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl border border-border font-semibold text-sm transition-all overflow-hidden",
              "hover:bg-red-500/5 hover:text-red-500 hover:border-red-500/30",
              isGenerating && "opacity-50 cursor-not-allowed"
            )}
          >
            <RotateCcw size={16} />
            {!isCollapsed && <span>开启新分析</span>}
          </button>
        </div>
      )}
    </motion.aside>
  );
}
