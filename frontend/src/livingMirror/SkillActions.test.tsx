import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { SkillActions } from './SkillActions';
import { sendGuardedCommand } from './commands';
import type { SkillContract } from './contracts';

vi.mock('./commands', () => ({ sendGuardedCommand: vi.fn() }));

const send = vi.mocked(sendGuardedCommand);
const MISSION_UUID = '00000000-0000-4000-8000-000000000001';

function makeSkill(state: string): SkillContract {
  return { skill_id: 'skill-1', version: 3, state } as unknown as SkillContract;
}

function fillRequired() {
  fireEvent.change(screen.getByLabelText('Goal'), { target: { value: '  Ship it  ' } });
  fireEvent.change(screen.getByLabelText('Enrolled project ID'), { target: { value: 'proj-9' } });
  fireEvent.change(screen.getByLabelText('Current scope'), { target: { value: 'repo' } });
  fireEvent.change(screen.getByLabelText('Validated project version'), { target: { value: 'v7' } });
}

function submitDraft() {
  const form = screen.getByText('Create governed draft').closest('form');
  if (!form) throw new Error('form not found');
  fireEvent.submit(form);
}

beforeEach(() => {
  send.mockReset();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('SkillActions', () => {
  it('only lets a candidate be activated after review, then records the result and refreshes', async () => {
    const refresh = vi.fn();
    send.mockResolvedValue({ status: 'accepted', data: { status: 'activated' }, message: 'raw' } as never);
    render(<SkillActions skill={makeSkill('candidate')} available refresh={refresh} />);

    const button = screen.getByRole('button', { name: 'Activate version 3' });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(send).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText(/I reviewed this version/));
    expect(button).toBeEnabled();
    fireEvent.click(button);

    expect(
      await screen.findByText('Version 3 activation recorded. Refreshing its lifecycle.'),
    ).toBeInTheDocument();
    expect(send).toHaveBeenCalledTimes(1);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText(/I reviewed this version/)).not.toBeChecked();
  });

  it('offers no activation for a skill that is not a candidate', () => {
    render(<SkillActions skill={makeSkill('active')} available refresh={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /Activate version/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/I reviewed this version/)).not.toBeInTheDocument();
  });

  it('rejects non-string JSON values locally without sending a command', async () => {
    render(<SkillActions skill={makeSkill('active')} available refresh={vi.fn()} />);
    fillRequired();
    fireEvent.change(screen.getByLabelText('Current inputs (JSON)'), { target: { value: '{"a":1}' } });
    submitDraft();

    expect(
      await screen.findByText('Inputs and project state must be JSON objects with string values.'),
    ).toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
  });

  it('sends a trimmed reuse request and shows the created draft id', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(MISSION_UUID);
    const refresh = vi.fn();
    send.mockResolvedValue({ status: 'accepted', data: { status: 'mission_created' }, message: 'raw' } as never);
    render(<SkillActions skill={makeSkill('active')} available refresh={refresh} />);

    fillRequired();
    fireEvent.change(screen.getByLabelText('Current inputs (JSON)'), { target: { value: '{"k":"v"}' } });
    submitDraft();

    expect(
      await screen.findByText('Governed mission draft created. Approval and execution remain separate.'),
    ).toBeInTheDocument();
    expect(screen.getByText(`reuse-${MISSION_UUID}`)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Inspect missions' })).toBeInTheDocument();
    expect(send).toHaveBeenCalledTimes(1);
    expect(send.mock.calls[0][1]).toMatchObject({
      skill_id: 'skill-1',
      version: 3,
      mission_id: `reuse-${MISSION_UUID}`,
      goal: 'Ship it',
      project_id: 'proj-9',
      current_scope: 'repo',
      current_inputs: { k: 'v' },
      current_state: {},
      validated_version: 'v7',
    });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('reports an escalated reuse with its reason and creates no draft', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(MISSION_UUID);
    send.mockResolvedValue({
      status: 'accepted',
      data: { status: 'escalate', reason: 'scope mismatch' },
      message: 'raw',
    } as never);
    render(<SkillActions skill={makeSkill('active')} available refresh={vi.fn()} />);

    fillRequired();
    submitDraft();

    expect(await screen.findByText('Reuse escalated: scope mismatch')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Inspect missions' })).not.toBeInTheDocument();
  });
});
