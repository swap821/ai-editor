'use client';

import { Component, type ErrorInfo, type ReactNode } from 'react';
import { publishCognition } from '@/lib/cognitionBus';

interface Props {
  children: ReactNode;
  name: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class SubsystemErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`Subsystem [${this.props.name}] crashed:`, error, errorInfo);
    
    publishCognition({
      type: 'terminal',
      label: `SYS.ERR`,
      detail: `Subsystem [${this.props.name}] encountered a fatal geometric/shader fault and was excised to preserve core cognition.`,
      source: 'subsystem-boundary',
      intensity: 0.8,
    });
  }

  public render() {
    if (this.state.hasError) {
      // Silent geometric degradation: simply do not render the subsystem.
      // This prevents React/R3F from crashing the broader canvas context.
      return null;
    }

    return this.props.children;
  }
}
