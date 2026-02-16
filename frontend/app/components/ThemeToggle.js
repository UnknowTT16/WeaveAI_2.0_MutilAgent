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
      className="relative p-2 rounded-xl bg-gray-100 dark:bg-white/5 border border-black/5 dark:border-white/10 hover:scale-105 active:scale-95 transition-all group overflow-hidden"
      aria-label="Toggle Theme"
    >
      <div className="absolute inset-0 bg-gradient-to-tr from-gemini-blue/10 to-gemini-purple/10 opacity-0 group-hover:opacity-100 transition-opacity" />
      
      <AnimatePresence mode="wait" initial={false}>
        {theme === 'dark' ? (
          <motion.div
            key="moon"
            initial={{ y: 20, opacity: 0, rotate: 45 }}
            animate={{ y: 0, opacity: 1, rotate: 0 }}
            exit={{ y: -20, opacity: 0, rotate: -45 }}
            transition={{ type: 'spring', stiffness: 200, damping: 15 }}
          >
            <Moon size={18} className="text-blue-400" />
          </motion.div>
        ) : (
          <motion.div
            key="sun"
            initial={{ y: 20, opacity: 0, rotate: 45 }}
            animate={{ y: 0, opacity: 1, rotate: 0 }}
            exit={{ y: -20, opacity: 0, rotate: -45 }}
            transition={{ type: 'spring', stiffness: 200, damping: 15 }}
          >
            <Sun size={18} className="text-amber-500" />
          </motion.div>
        )}
      </AnimatePresence>
    </button>
  );
}
