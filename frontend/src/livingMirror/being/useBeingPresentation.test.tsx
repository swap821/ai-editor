import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { __resetTabStoreForTests } from '../../superbrain/lib/tabStore';
import { useMirrorStore } from '../../superbrain/lib/mirrorStore';
import { setEmergencyStopPresentation } from '../emergencyStopPresentation';
import { useBeingPresentation } from './useBeingPresentation';

function Probe() {
  const presentation = useBeingPresentation();
  return <output data-testid="being-posture">{presentation.phase}:{presentation.motion}:{presentation.taskState}</output>;
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
});

