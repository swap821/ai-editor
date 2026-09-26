import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { __resetTabStoreForTests } from '../../superbrain/lib/tabStore';
import {
  bodyMotionProfileForPosture,
  deriveBodyPosture,
  lifecyclePhaseForPhysicalProjection,
} from '../../superbrain/lib/bodyPosture';
import { useMirrorStore } from '../../superbrain/lib/mirrorStore';
import { derivePhysicalSnapshot } from './physicalSnapshot';
import { setEmergencyStopPresentation } from '../emergencyStopPresentation';
import { useBeingPresentation } from './useBeingPresentation';

function Probe() {
  const presentation = useBeingPresentation();
  return <output data-testid="being-posture">{presentation.phase}:{presentation.motion}:{presentation.taskState}</output>;
}

function ProjectionParityProbe() {
  const presentation = useBeingPresentation();
  const physical = derivePhysicalSnapshot(presentation);
  const posture = deriveBodyPosture({ phase: lifecyclePhaseForPhysicalProjection(physical), physical });
  const motion = bodyMotionProfileForPosture(posture);
  return <>
    <output data-testid="dom-projection">{JSON.stringify({
      phase: presentation.phase,
      taskState: presentation.taskState,
      workers: presentation.workers.map(({ workerId, state }) => ({ workerId, state })),
    })}</output>
    <output data-testid="scene-projection">{JSON.stringify({
      phase: physical.phase,
      taskState: physical.taskState,
      workers: physical.branches.map(({ workerId, state }) => ({ workerId, state })),
    })}</output>
    <output data-testid="body-motion">{JSON.stringify(motion)}</output>
  </>;
}

function admitWorkerRoster(cursor: number, activeWorkers: string[]) {
  act(() => {
    useMirrorStore.getState().setConnection('connected');
    useMirrorStore.getState().setSnapshot({
      last_event_id: cursor,
      status: 'online',
      phase: 'active',
      active_workers: activeWorkers,
    });
    expect(useMirrorStore.getState().confirmFresh(cursor)).toBe(true);
  });
}

describe('useBeingPresentation', () => {
  beforeEach(() => {
    setEmergencyStopPresentation('unknown');
    __resetTabStoreForTests();
    useMirrorStore.setState({
      status: 'offline',
      connection: 'disconnected',
      projection: 'unknown',
      snapshotReceivedAt: null,
      recentEvents: [],
      lastEventId: null,
      lastTurnStartedEventId: null,
      lastVerificationEventId: null,
      approvalRequired: false,
      workers: {},
      verifications: {},
      lastVerification: null,
      phase: 'unknown',
      pendingEvents: 0,
    });
  });

  it('projects an engaged measured latch as a stopped body posture', () => {
    render(<Probe />);
    expect(screen.getByTestId('being-posture')).toHaveTextContent('degraded:calm:idle');

    act(() => {
      setEmergencyStopPresentation('engaged');
    });

    expect(screen.getByTestId('being-posture')).toHaveTextContent('stopped:stop:stopped');
  });

  it('keeps a cold worker snapshot, roster reorder, and stale recovery aligned from DOM through body motion', () => {
    render(<ProjectionParityProbe />);

    admitWorkerRoster(40, ['worker-beta', 'worker-alpha']);
    const domCold = JSON.parse(screen.getByTestId('dom-projection').textContent ?? 'null');
    const sceneCold = JSON.parse(screen.getByTestId('scene-projection').textContent ?? 'null');
    expect(sceneCold).toEqual(domCold);
    expect(domCold.workers.map((worker: { workerId: string }) => worker.workerId)).toEqual(['worker-alpha', 'worker-beta']);
    expect(JSON.parse(screen.getByTestId('body-motion').textContent ?? 'null')).toEqual({
      pulseRate: 4.4,
      breathGain: 0.256,
      rootExcitation: 0.56,
    });

    admitWorkerRoster(55, ['worker-alpha', 'worker-gamma', 'worker-beta']);
    const domReordered = JSON.parse(screen.getByTestId('dom-projection').textContent ?? 'null');
    const sceneReordered = JSON.parse(screen.getByTestId('scene-projection').textContent ?? 'null');
    expect(sceneReordered).toEqual(domReordered);
    expect(domReordered.workers.map((worker: { workerId: string }) => worker.workerId)).toEqual([
      'worker-alpha', 'worker-beta', 'worker-gamma',
    ]);

    act(() => useMirrorStore.getState().markStale('test replay gap'));
    expect(useMirrorStore.getState().phase).toBe('active');
    const domStale = JSON.parse(screen.getByTestId('dom-projection').textContent ?? 'null');
    const sceneStale = JSON.parse(screen.getByTestId('scene-projection').textContent ?? 'null');
    expect(sceneStale).toEqual(domStale);
    expect(domStale.phase).toBe('stale');
    expect(domStale.workers).toEqual([]);
    expect(JSON.parse(screen.getByTestId('body-motion').textContent ?? 'null')).toEqual({
      pulseRate: 1.8,
      breathGain: 0,
      rootExcitation: 0,
    });
  });
});

