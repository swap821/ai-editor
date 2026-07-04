import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const { fetchOperatorModel } = vi.hoisted(() => ({ fetchOperatorModel: vi.fn() }));

vi.mock('../superbrain/lib/aiosAdapter', async () => {
  const actual = await vi.importActual<typeof import('../superbrain/lib/aiosAdapter')>(
    '../superbrain/lib/aiosAdapter',
  );
  return {
    ...actual,
    fetchOperatorModel,
  };
});

import OperatorProfileCard from './OperatorProfileCard';

describe('OperatorProfileCard', () => {
  beforeEach(() => {
    fetchOperatorModel.mockReset();
  });

  it('renders an empty state when the operator model is empty', async () => {
    fetchOperatorModel.mockResolvedValue({ preferences: [], attributes: {}, projectContext: [] });

    render(<OperatorProfileCard />);

    await waitFor(() => {
      expect(screen.getByText('No operator model yet')).toBeInTheDocument();
    });
  });

  it('renders preferences, attributes, and project context when present', async () => {
    fetchOperatorModel.mockResolvedValue({
      preferences: [{ predicate: 'prefers', object: 'dark mode' }],
      attributes: { role: 'engineer' },
      projectContext: [{ predicate: 'uses', object: 'FastAPI' }],
    });

    render(<OperatorProfileCard />);

    await waitFor(() => {
      expect(screen.getByText('Preferences')).toBeInTheDocument();
    });
    expect(screen.getByText('dark mode')).toBeInTheDocument();
    expect(screen.getByText('About You')).toBeInTheDocument();
    expect(screen.getByText('engineer')).toBeInTheDocument();
    expect(screen.getByText('Project')).toBeInTheDocument();
    expect(screen.getByText('FastAPI')).toBeInTheDocument();
    expect(screen.queryByText('No operator model yet')).not.toBeInTheDocument();
  });
});
