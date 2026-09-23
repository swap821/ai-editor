import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import GuidedTaskPanel from './GuidedTaskPanel';

const response = (value: unknown) => ({
  ok: true,
  status: 200,
  json: () => Promise.resolve(value),
} as Response);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('GuidedTaskPanel', () => {
  it('projects measured task records without exposing technical mission vocabulary or identifiers', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response({
      count: 1,
      missions: [{
        family: 'council',
        missionId: 'mission-secret-42',
        mission: 'Prepare release notes',
        status: 'deliberating',
        risk: 'yellow',
        updatedAt: 1789400000,
        approvalNeeded: true,
        verificationPassed: null,
        verificationStrength: null,
        verificationMeetsFloor: null,
      }],
    }))));

    render(<GuidedTaskPanel />);

    expect(await screen.findByRole('heading', { name: 'Tasks' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Prepare release notes' })).toBeInTheDocument();
    expect(screen.getByText('Permission needed before GAGOS can continue.')).toBeInTheDocument();
    expect(screen.getByText('Verification status is not available yet.')).toBeInTheDocument();
    expect(screen.queryByText(/mission-secret-42|council|authority|worker|deliberat/i)).not.toBeInTheDocument();
  });
});
