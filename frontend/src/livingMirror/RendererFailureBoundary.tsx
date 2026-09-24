import { Component, type ErrorInfo, type ReactNode } from 'react';
import { RendererFallbackNotice } from './RendererFallbackNotice';

type RendererFailureBoundaryProps = {
  children: ReactNode;
  onRetry?: () => void;
};

type RendererFailureBoundaryState = {
  failed: boolean;
};

/**
 * Product-owned guard around the lazy organism import and renderer subtree.
 * The conversation, approval, stop, and workspace controls live outside this
 * boundary, so a visual failure cannot take the operational shell with it.
 */
export class RendererFailureBoundary extends Component<
  RendererFailureBoundaryProps,
  RendererFailureBoundaryState
> {
  public state: RendererFailureBoundaryState = { failed: false };

  public static getDerivedStateFromError(): RendererFailureBoundaryState {
    return { failed: true };
  }

  public componentDidCatch(_error: Error, _errorInfo: ErrorInfo): void {
    // The fallback is deliberately quiet: renderer errors must not leak
    // private application state or be mistaken for backend failures.
  }

  private handleRetry = (): void => {
    this.setState({ failed: false }, () => this.props.onRetry?.());
  };

  public render(): ReactNode {
    if (!this.state.failed) return this.props.children;

    return (
      <RendererFallbackNotice
        visible
        onRetry={this.props.onRetry ? this.handleRetry : undefined}
      />
    );
  }
}
