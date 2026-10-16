import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  __resetTabStoreForTests, focusWorkspace, getTabStoreSnapshot, openWorkspacePanel,
  pinWorkspace, showContentSurface, updateMaterializedTab,
} from '../superbrain/lib/tabStore';
import { LivingWorkspaceShell } from './LivingWorkspaceShell';

function viewport(initialWidth: number) {
  let width = initialWidth;
  const listeners = new Map<string, Set<(event: MediaQueryListEvent) => void>>();
  const matches = (query: string) => query === '(max-width: 767px)' ? width <= 767
    : query === '(max-width: 360px)' ? width <= 360 : false;
  vi.stubGlobal('matchMedia', vi.fn((query: string) => {
    const callbacks = listeners.get(query) ?? new Set();
    listeners.set(query, callbacks);
    return {
      media: query,
      get matches() { return matches(query); },
      addEventListener: (_type: string, callback: (event: MediaQueryListEvent) => void) => callbacks.add(callback),
      removeEventListener: (_type: string, callback: (event: MediaQueryListEvent) => void) => callbacks.delete(callback),
    };
  }));
  return (nextWidth: number) => {
    width = nextWidth;
    for (const [media, callbacks] of listeners) for (const callback of callbacks) {
      callback({ media, matches: matches(media) } as MediaQueryListEvent);
    }
  };
}

function result(index: number) {
  const id = showContentSurface({ filepath: `result-${index}.ts`, code: `result ${index}`, language: 'typescript',
    verifyOutput: `reported output ${index}` }).id;
  focusWorkspace(id);
  return id;
}

beforeEach(() => __resetTabStoreForTests());
afterEach(() => { __resetTabStoreForTests(); vi.unstubAllGlobals(); });

describe('Guided narrow workspace chooser', () => {
  it('reaches every open result in the existing heading without exposing Expert-only panels', async () => {
    viewport(390);
    await act(async () => { render(<LivingWorkspaceShell />); });
    let ids: string[] = [];
    act(() => {
      openWorkspacePanel('terminal', 'Terminal');
      openWorkspacePanel('history', 'Recent activity');
      ids = Array.from({ length: 6 }, (_, index) => result(index));
      pinWorkspace(ids[0]);
    });
    const chooser = screen.getByRole('combobox', { name: 'Choose workspace' });
    expect(chooser.closest('.lm-surface__header')).toBeTruthy();
    const options = within(chooser).getAllByRole('option');
    expect(options).toHaveLength(7);
    expect(options.map((option) => (option as HTMLOptionElement).value)).toEqual(['history', ...ids]);
    expect(within(chooser).getByRole('option', { name: /result-0.ts.*pinned/ })).toBeInTheDocument();
    expect(within(chooser).queryByRole('option', { name: /Terminal/ })).not.toBeInTheDocument();
    fireEvent.change(chooser, { target: { value: ids[0] } });
    expect(getTabStoreSnapshot().focusId).toBe(ids[0]);
    expect(screen.getByRole('heading', { name: 'result-0.ts', level: 2 })).toHaveFocus();
    expect(screen.getByText('result 0')).toBeVisible();
  });

  it('switches readers without remounting their content, scroll or expanded check output', async () => {
    viewport(320);
    await act(async () => { render(<LivingWorkspaceShell />); });
    let first = ''; let second = '';
    act(() => { first = result(1); });
    const code = screen.getByText('result 1');
    const body = code.closest<HTMLElement>('.lm-surface__body')!;
    const output = screen.getByText('Reported check output').closest('details')!;
    fireEvent.click(screen.getByText('Reported check output'));
    body.scrollTop = 80;
    fireEvent.scroll(body);
    act(() => { second = result(2); });
    expect(code).toBeInTheDocument();
    expect(code).not.toBeVisible();
    expect(body).toHaveAttribute('inert');
    act(() => updateMaterializedTab(first, {
      content: { filepath: 'result-1.ts', code: 'updated first result', language: 'typescript', verifyOutput: 'later output' },
    }));
    const chooser = screen.getByRole('combobox', { name: 'Choose workspace' });
    fireEvent.change(chooser, { target: { value: first } });
    expect(screen.getByText('updated first result')).toBe(code);
    expect(body).not.toHaveAttribute('inert');
    expect(body.scrollTop).toBe(80);
    expect(output).toHaveAttribute('open');
    fireEvent.change(chooser, { target: { value: second } });
    expect(screen.getByText('result 2')).toBeVisible();
    expect(getTabStoreSnapshot().tabs.filter((tab) => tab.kind === 'content').map((tab) => tab.id)).toEqual([first, second]);
  });

  it('leaves the result open when Escape cancels the native chooser, retaining normal heading Escape', async () => {
    viewport(390);
    await act(async () => { render(<LivingWorkspaceShell />); });
    let selected = '';
    act(() => { result(1); selected = result(2); });
    const chooser = screen.getByRole('combobox', { name: 'Choose workspace' });
    chooser.focus();
    fireEvent.keyDown(chooser, { key: 'Escape' });
    expect(getTabStoreSnapshot().focusId).toBe(selected);
    expect(getTabStoreSnapshot().recoverableTabs ?? []).toHaveLength(0);
    expect(chooser).toHaveFocus();
    fireEvent.keyDown(screen.getByRole('heading', { name: 'result-2.ts', level: 2 }), { key: 'Escape' });
    expect(getTabStoreSnapshot().recoverableTabs?.map((tab) => tab.id)).toContain(selected);
  });

  it('hands keyboard focus to the retained heading when responsive or mode controls replace the chooser', async () => {
    const resize = viewport(390);
    let view: ReturnType<typeof render>;
    await act(async () => { view = render(<LivingWorkspaceShell />); });
    act(() => { result(1); result(2); });
    screen.getByRole('combobox', { name: 'Choose workspace' }).focus();
    act(() => resize(1280));
    expect(screen.queryByRole('combobox', { name: 'Choose workspace' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'result-2.ts', level: 2 })).toHaveFocus();
    act(() => resize(390));
    screen.getByRole('combobox', { name: 'Choose workspace' }).focus();
    view!.rerender(<LivingWorkspaceShell experienceMode="expert" />);
    expect(screen.queryByRole('combobox', { name: 'Choose workspace' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'result-2.ts', level: 2 })).toHaveFocus();
  });

  it('does not steal draft focus across a resize, and avoids a chooser for zero or one open view', async () => {
    const resize = viewport(390);
    await act(async () => { render(<><input aria-label="Unsent draft" /><LivingWorkspaceShell /></>); });
    expect(screen.queryByRole('combobox', { name: 'Choose workspace' })).not.toBeInTheDocument();
    act(() => { result(1); });
    expect(screen.queryByRole('combobox', { name: 'Choose workspace' })).not.toBeInTheDocument();
    act(() => { result(2); });
    const draft = screen.getByRole('textbox', { name: 'Unsent draft' });
    fireEvent.change(draft, { target: { value: 'keep this unsent' } });
    draft.focus();
    act(() => resize(1280));
    expect(draft).toHaveFocus();
    expect(draft).toHaveValue('keep this unsent');
    act(() => resize(390));
    expect(draft).toHaveFocus();
  });

  it('keeps all twelve results selectable at capacity and numbers repeated titles without inventing paths', async () => {
    viewport(390);
    await act(async () => { render(<LivingWorkspaceShell />); });
    let ids: string[] = [];
    act(() => {
      ids = Array.from({ length: 12 }, (_, index) => result(index));
      for (const id of ids) updateMaterializedTab(id, { content: {
        filepath: 'same.ts', code: id, language: 'typescript',
      } });
    });
    const chooser = screen.getByRole('combobox', { name: 'Choose workspace' });
    const options = within(chooser).getAllByRole('option');
    expect(options.map((option) => option.textContent)).toEqual(ids.map((_, index) => `${index + 1}. same.ts`));
    fireEvent.change(chooser, { target: { value: ids[0] } });
    expect(getTabStoreSnapshot().focusId).toBe(ids[0]);
    expect(screen.getByText(ids[0])).toBeVisible();
  });
});
