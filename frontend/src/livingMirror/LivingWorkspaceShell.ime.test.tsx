import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it } from 'vitest';
import { __resetTabStoreForTests, getTabStoreSnapshot, openWorkspacePanel } from '../superbrain/lib/tabStore';
import { LivingWorkspaceShell } from './LivingWorkspaceShell';

beforeEach(() => __resetTabStoreForTests());
afterEach(() => __resetTabStoreForTests());

it.each([{ isComposing: true }, { keyCode: 229 }])('keeps the active terminal and its draft when Escape belongs to an input method (%j)', async (composition) => {
  render(<LivingWorkspaceShell experienceMode="expert" />);
  act(() => openWorkspacePanel('terminal', 'Terminal'));
  const draft = await screen.findByPlaceholderText('Type a command...', undefined, { timeout: 5000 });
  fireEvent.change(draft, { target: { value: 'unfinished draft' } });
  draft.focus();
  fireEvent.keyDown(draft, { key: 'Escape', ...composition });
  expect(getTabStoreSnapshot().focusId).toBe('terminal');
  expect(draft).toHaveFocus();
  expect(draft).toHaveValue('unfinished draft');
  fireEvent.keyDown(draft, { key: 'Escape', isComposing: false });
  expect(getTabStoreSnapshot().focusId).not.toBe('terminal');
});
