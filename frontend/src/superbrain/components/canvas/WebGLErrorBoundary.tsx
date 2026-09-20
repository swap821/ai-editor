'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { FallbackScene } from './FallbackScene';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onRetry?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export function WebGLFallback({ onRetry }: { onRetry?: () => void }) {
  return (
    <div className="webgl-fallback" role="alert" aria-live="assertive">
      <FallbackScene posture="idle" />
      <div className="webgl-fallback__panel">
        <p className="webgl-fallback__eyebrow">3D presence</p>
        <h2>GAGOS is still here</h2>
        <p>
          The 3D presence is unavailable right now. Conversation and workspaces remain available.
        </p>
        {onRetry ? (
          <button type="button" onClick={() => { onRetry(); }}>
            Retry 3D presence
          </button>
        ) : (
          <p className="webgl-fallback__note">Restore graphics support to bring the 3D presence back.</p>
        )}
      </div>
    </div>
  );
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

      return <WebGLFallback onRetry={() => {
        this.setState({ hasError: false, error: null });
        this.props.onRetry?.();
      }} />;
    }

    return this.props.children;
  }
}
