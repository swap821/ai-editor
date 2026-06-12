'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class WebGLErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('WebGL/Canvas error caught by boundary:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      
      return (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#010307] text-slate-200 z-[9000]">
          <div className="flex flex-col items-center max-w-md p-8 border border-red-500/20 bg-black/50 backdrop-blur-md rounded-lg">
            <h2 className="text-xl font-bold tracking-wider mb-2 text-red-400 uppercase">GPU Acceleration Failed</h2>
            <p className="text-sm text-slate-400 text-center font-mono">
              The 3D environment encountered a fatal rendering error.
            </p>
            {this.state.error && (
              <p className="text-xs text-slate-500 font-mono mt-4 p-2 bg-black/40 rounded border border-slate-800 break-all">
                {this.state.error.message}
              </p>
            )}
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="mt-6 px-6 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-300 border border-red-500/30 rounded font-mono text-sm transition-colors uppercase tracking-widest focus:outline-none focus:ring-2 focus:ring-red-500/50"
            >
              Attempt Restart
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
