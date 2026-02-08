'use client';

import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 rounded-2xl bg-red-500/10 border border-red-500/30 text-center animate-fade-in-up">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-500/20 flex items-center justify-center">
            <span className="text-3xl">⚠️</span>
          </div>
          <h3 className="text-xl font-bold text-red-400 mb-2">组件渲染失败</h3>
          <p className="text-slate-400 mb-4 text-sm max-w-md mx-auto">
             我们遇到了一个意外错误。请尝试刷新页面，或联系支持团队。
          </p>
          <div className="p-4 bg-black/20 rounded-lg text-left overflow-auto max-h-40 border border-white/5 font-mono text-xs text-red-300">
            {this.state.error?.toString()}
          </div>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="mt-6 px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-300 rounded-lg transition-colors border border-red-500/30"
          >
            重试
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
