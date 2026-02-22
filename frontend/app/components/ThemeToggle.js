'use client';

import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';
import { Sun, Moon } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) return <div className="w-9 h-9" />;

  return (
    <button
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      className="relative rounded-xl border border-border bg-card p-2 text-muted-foreground transition-transform duration-200 hover:scale-105 hover:text-foreground active:scale-95"
      aria-label={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
    >
      <AnimatePresence mode="wait" initial={false}>
        {theme === 'dark' ? (
          <motion.div
            key="moon"
            initial={{ y: 20, opacity: 0, rotate: 45 }}
            animate={{ y: 0, opacity: 1, rotate: 0 }}
            exit={{ y: -20, opacity: 0, rotate: -45 }}
            transition={{ type: 'spring', stiffness: 200, damping: 15 }}
          >
            <Moon size={18} className="text-gemini-blue" aria-hidden="true" />
          </motion.div>
        ) : (
          <motion.div
            key="sun"
            initial={{ y: 20, opacity: 0, rotate: 45 }}
            animate={{ y: 0, opacity: 1, rotate: 0 }}
            exit={{ y: -20, opacity: 0, rotate: -45 }}
            transition={{ type: 'spring', stiffness: 200, damping: 15 }}
          >
            <Sun size={18} className="text-amber-500" aria-hidden="true" />
          </motion.div>
        )}
      </AnimatePresence>
    </button>
  );
}
