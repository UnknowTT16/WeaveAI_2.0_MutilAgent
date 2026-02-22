'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { useEffect, useRef } from 'react';

export default function CommandModal({ isOpen, onClose, children }) {
  const panelRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      panelRef.current?.focus();
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const onEsc = (event) => {
      if (event.key === 'Escape') {
        onClose?.();
      }
    };

    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6" role="presentation">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-background/80 backdrop-blur-sm dark:bg-black/60"
          />

          <motion.div
            ref={panelRef}
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: 'spring', damping: 20, stiffness: 300 }}
            className="relative w-full max-w-2xl glass rounded-[2.5rem] shadow-2xl overflow-hidden border border-border"
            role="dialog"
            aria-modal="true"
            aria-label="战略配置弹窗"
            tabIndex={-1}
          >
            <button
              type="button"
              onClick={onClose}
              className="absolute right-6 top-6 p-2 rounded-full hover:bg-accent transition-colors z-10"
              aria-label="关闭弹窗"
            >
              <X size={20} className="text-muted-foreground" aria-hidden="true" />
            </button>

            <div className="p-8 sm:p-12">
              {children}
            </div>

            <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-background/10 to-transparent pointer-events-none" />
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
