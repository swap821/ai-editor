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

  it('renders a new file as all additions (create_file preview)', () => {
    // create_file builds an all-additions diff ("" -> content), e.g. via
    // difflib.unified_diff([], content, fromfile="/dev/null", tofile="b/new.py").
    const diff = '--- /dev/null\n+++ b/new.py\n@@ -0,0 +1,2 @@\n+print("hi")\n+x = 1\n';
    render(<DiffView diff={diff} />);
    expect(screen.getByText('+print("hi")')).toBeInTheDocument();
    expect(screen.getByText('+x = 1')).toBeInTheDocument();
  });
});
