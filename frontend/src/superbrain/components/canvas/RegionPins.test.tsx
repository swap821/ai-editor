import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';

import { PinChip } from '@/components/canvas/RegionPins';

vi.mock('@/lib/metricsStore', () => ({
  useMetric: () => 42,
  useMetricHistory: () => [30, 50, 42],
}));

vi.mock('@react-three/drei', () => ({
  Html: ({ children }: { children: React.ReactNode }) => <div data-testid="html-mock">{children}</div>,
}));

const pin = {
  key: 'research' as const,
  name: 'RESEARCH',
  anchor: new THREE.Vector3(0, 0, 0),
  reach: 0.1,
  nudge: new THREE.Vector3(0, 0, 0),
};

describe('RegionPins · PinChip', () => {
  it('toggles open on Enter and Space, exposes aria-expanded, and shows history only when open', () => {
    render(<PinChip pin={pin} label={new THREE.Vector3(0, 0, 0)} />);

    const chip = screen.getByRole('button', { name: /RESEARCH/ });
    expect(chip).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText('RESEARCH history')).not.toBeInTheDocument();

    fireEvent.keyDown(chip, { key: 'Enter' });
    expect(chip).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText('RESEARCH history')).toBeInTheDocument();

    fireEvent.keyDown(chip, { key: ' ' });
    expect(chip).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText('RESEARCH history')).not.toBeInTheDocument();
  });
});
