import { cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as dashboardModule from './WorkTabLiveDashboard';

vi.mock('@/lib/metricsStore', () => ({
  useMetric: (key: string) =>
    ({ research: 0, memory: 33, tools: 66, signals: 99 })[key],
  useMetricHistory: () => [0, 99],
}));

vi.mock('@react-three/drei', () => ({
  Text: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  Line: ({ points }: { points: number[][] }) => (
    <div data-testid="sparkline" data-points={JSON.stringify(points)} />
  ),
}));

const Dashboard = Object.values(dashboardModule)[0];
const theme = {
  live: '#00ff00',
  outline: '#111111',
  muted: '#222222',
  accent: '#333333',
  header: '#444444',
} as unknown as Parameters<typeof Dashboard>[0]['theme'];

afterEach(cleanup);

describe('WorkTabLiveDashboard', () => {
  it('renders the heading and all four channel labels', () => {
    render(<Dashboard width={100} height={10} z={3} theme={theme} />);

    expect(screen.getByText('LIVE · BODY')).toBeTruthy();
    expect(['R', 'M', 'T', 'S'].map((label) => screen.getByText(label).textContent))
      .toEqual(['R', 'M', 'T', 'S']);
  });

  it('positions the bars according to their metric values', () => {
    const { container } = render(
      <Dashboard width={100} height={10} z={3} theme={theme} />,
    );

    const meshes = container.querySelectorAll('mesh');
    expect(meshes).toHaveLength(8);

    const foregroundPositions = [1, 3, 5, 7].map((index) =>
      meshes[index].getAttribute('position')?.split(',').map(Number),
    );

    expect(foregroundPositions[0]?.[0]).toBeCloseTo(8);
    expect(foregroundPositions[0]?.[1]).toBeCloseTo(-0.798);
    expect(foregroundPositions[1]?.[0]).toBeCloseTo(17);
    expect(foregroundPositions[1]?.[1]).toBeCloseTo(-0.8 + 1 / 3);
    expect(foregroundPositions[2]?.[0]).toBeCloseTo(26);
    expect(foregroundPositions[2]?.[1]).toBeCloseTo(-0.8 + 2 / 3);
    expect(foregroundPositions[3]).toEqual([35, 0.19999999999999996, 3]);
  });

  it('maps tools history to sparkline points', () => {
    render(<Dashboard width={100} height={10} z={3} theme={theme} />);

    const points = JSON.parse(
      screen.getByTestId('sparkline').getAttribute('data-points') ?? '[]',
    ) as number[][];

    expect(points).toHaveLength(2);
    expect(points[0][0]).toBeCloseTo(3.95);
    expect(points[0][1]).toBeCloseTo(1.7);
    expect(points[0][2]).toBe(3);
    expect(points[1][0]).toBeCloseTo(35.95);
    expect(points[1][1]).toBeCloseTo(2.3);
    expect(points[1][2]).toBe(3);
  });
});
