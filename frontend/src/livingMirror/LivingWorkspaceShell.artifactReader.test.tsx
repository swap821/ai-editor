import { act, cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { LivingWorkspaceShell } from './LivingWorkspaceShell';
import { __resetTabStoreForTests, focusWorkspace, showContentSurface, updateMaterializedTab } from '../superbrain/lib/tabStore';
import { __resetSovereignIdentityForTests } from '../superbrain/lib/sovereignIdentity';

// Only HTTP is external. The actual reader, persistence and artifact owners run.
beforeEach(() => {
  __resetTabStoreForTests(); __resetSovereignIdentityForTests();
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })));
});
afterEach(() => {
  cleanup(); __resetTabStoreForTests(); __resetSovereignIdentityForTests(); vi.unstubAllGlobals();
});

it('describes the focused same-path code with its own replay uncertainty, not the older result', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
  act(() => {
    showContentSurface({ filepath: 'same.py', code: 'older verified code', language: 'python', verifyVerdict: 'pass' });
    const next = showContentSurface({ filepath: 'writing', code: 'new partial code', language: 'python' });
    updateMaterializedTab(next.id, { content: { filepath: 'same.py', code: 'new partial code', language: 'python', completion: 'awaiting-replay' } });
    focusWorkspace(next.id);
  });
  const code = screen.getByText('new partial code');
  code.focus();
  expect(code).toHaveFocus();
  expect(code).toHaveAccessibleDescription('Permission submitted. Waiting for the replay response; completion is unconfirmed. Generated artifact · Project effects require separate receipts.');
  expect(within(code.closest<HTMLElement>('.lm-surface__body')!).getByRole('status')).toHaveTextContent(/completion is unconfirmed/);
});

it('keeps the same keyboard reader and retires only its obsolete partial description on completion', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="beginner" />); });
  let id = '';
  act(() => { id = showContentSurface({ filepath: 'result.py', code: 'first chunk', language: 'python', streaming: true }).id; });
  const code = screen.getByText('first chunk');
  code.focus();
  expect(code).toHaveAccessibleDescription('Partial result; no completed outcome is established. Generated artifact · Project effects require separate receipts.');
  act(() => updateMaterializedTab(id, { content: { filepath: 'result.py', code: 'final code', language: 'python', streaming: false } }));
  expect(screen.getByText('final code')).toBe(code);
  expect(code).toHaveFocus();
  expect(code).toHaveAccessibleDescription('Generated artifact · Project effects require separate receipts.');
  expect(screen.queryByText('Partial result; no completed outcome is established.')).not.toBeInTheDocument();
});
