import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProductSpaces from './ProductSpaces';

const mirror = vi.hoisted(() => ({
  current: {
    status: 'offline',
    pendingEvents: 0,
    phase: 'idle',
    activeCastes: [],
    activeMissions: [],
    activeWorkers: [],
    activeModels: [],
    approvalRequired: false,
    lastVerification: null,
    lastAnnouncement: null,
    snapshotRequired: false,
    recentEvents: [],
    lastEventId: null,
    bootFacts: null,
  },
}));

vi.mock('../superbrain/lib/mirrorStore', () => ({
  useMirrorStore: () => mirror.current,
}));

vi.mock('./CouncilDashboard', () => ({
  default: () => <div data-testid="actual-council">Actual Council mission state</div>,
}));

vi.mock('./FileTree', () => ({
  default: ({ onOpenFile, onClose }) => (
    <div data-testid="project-tree">
      <button type="button" onClick={() => onOpenFile({ name: 'README.md', path: 'README.md' })}>Open README</button>
      <button type="button" onClick={onClose}>Close tree</button>
    </div>
  ),
}));

vi.mock('./CodeEditor', () => ({
  default: ({ file, onClose }) => (
    <div data-testid="code-editor">
      Editing {file.name}
      <button type="button" onClick={onClose}>Close editor</button>
    </div>
  ),
}));

describe('ProductSpaces', () => {
  beforeEach(() => {
    mirror.current = {
      status: 'offline',
      pendingEvents: 0,
      phase: 'idle',
      activeCastes: [],
      activeMissions: [],
      activeWorkers: [],
      activeModels: [],
      approvalRequired: false,
      lastVerification: null,
      lastAnnouncement: null,
      snapshotRequired: false,
      recentEvents: [],
      lastEventId: null,
      bootFacts: null,
    };
  });

  it('opens on a truthful Living Mind portrait with unavailable backend state', () => {
    render(<ProductSpaces />);

    expect(screen.getByRole('heading', { name: 'Living Mind' })).toBeInTheDocument();
    expect(screen.getByText('Control plane')).toBeInTheDocument();
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
    expect(screen.getByText('Control plane unavailable')).toBeInTheDocument();
  });

  it('keeps work surfaces closed until the operator opens them', () => {
    render(<ProductSpaces />);
    fireEvent.click(screen.getByRole('button', { name: /Workbench/ }));

    expect(screen.getByRole('heading', { name: 'Workbench' })).toBeInTheDocument();
    expect(screen.getByText('Closed by default')).toBeInTheDocument();
    expect(screen.queryByTestId('project-tree')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Open project tree/ }));
    expect(screen.getByTestId('project-tree')).toBeInTheDocument();
  });

  it('shows the actual Council surface in Governance', () => {
    render(<ProductSpaces />);
    fireEvent.click(screen.getByRole('button', { name: /Governance/ }));

    expect(screen.getByRole('heading', { name: 'Governance' })).toBeInTheDocument();
    expect(screen.getByTestId('actual-council')).toBeInTheDocument();
  });

  it('labels an empty History space instead of inventing events', () => {
    render(<ProductSpaces />);
    fireEvent.click(screen.getByRole('button', { name: /History/ }));

    expect(screen.getByRole('heading', { name: 'History' })).toBeInTheDocument();
    expect(screen.getByText('No operational events have been reported.')).toBeInTheDocument();
  });
});
