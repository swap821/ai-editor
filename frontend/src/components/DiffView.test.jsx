import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import DiffView from './DiffView';

describe('DiffView', () => {
  it('renders added and removed lines from a unified diff', () => {
    const diff = '--- a/x\n+++ b/x\n@@ -1 +1 @@\n-hello world\n+hello there\n';
    render(<DiffView diff={diff} />);
    expect(screen.getByText('-hello world')).toBeInTheDocument();
    expect(screen.getByText('+hello there')).toBeInTheDocument();
  });

  it('renders without crashing on an empty diff', () => {
    render(<DiffView diff="" />);
    expect(screen.getByTestId('diff-view')).toBeInTheDocument();
  });
});
