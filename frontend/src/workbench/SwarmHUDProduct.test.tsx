import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { act } from 'react';
import SwarmHUD from '../superbrain/components/ui/SwarmHUD';
import { startSwarmPlan, markSwarmCloudSubtask, resetSwarmHUD } from '../superbrain/lib/swarmHUDStore';

describe('SwarmHUD product integration', () => {
  it('highlights a cloud-routed subtask with a cloud badge', () => {
    resetSwarmHUD();
    render(<SwarmHUD />);

    act(() => {
      startSwarmPlan(['cloud task', 'local task']);
      markSwarmCloudSubtask(0);
    });

    expect(screen.getByText('cloud task')).toBeInTheDocument();
    expect(screen.getByLabelText('cloud')).toBeInTheDocument();
    expect(screen.getByText(/1 cloud/)).toBeInTheDocument();
  });
});
