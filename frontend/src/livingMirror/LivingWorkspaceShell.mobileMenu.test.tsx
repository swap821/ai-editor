import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { __resetTabStoreForTests, openWorkspacePanel } from '../superbrain/lib/tabStore';
import { LivingWorkspaceShell } from './LivingWorkspaceShell';

afterEach(() => {
  __resetTabStoreForTests();
  vi.unstubAllGlobals();
});

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
    for (const [media, callbacks] of listeners) {
      for (const callback of callbacks) callback({ media, matches: matches(media) } as MediaQueryListEvent);
    }
  };
}

describe('LivingWorkspaceShell mobile Expert menu handoff', () => {
  it('resets toolbar scroll at the mobile breakpoint without resetting work content', async () => {
    const resize = viewport(1280);
    await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
    act(() => openWorkspacePanel('test', 'Test workspace', 'fixture'));
    const navigation = screen.getByRole('navigation', { name: 'Workspaces' });
    const body = screen.getByRole('region', { name: 'Selected workspace' }).querySelector<HTMLElement>('.lm-surface__body')!;
    navigation.scrollLeft = 160;
    body.scrollTop = 80;
    fireEvent.scroll(body);

    act(() => resize(320));
    expect(navigation.scrollLeft).toBe(0);
    expect(body).toBeInTheDocument();
    expect(body.scrollTop).toBe(80);
  });

  it('makes every open view and motion control reachable from one mobile menu, with safe same-workspace focus', async () => {
    viewport(390);
    await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
    act(() => { for (let i = 0; i < 6; i++) openWorkspacePanel(`test-${i}`, `Test workspace ${i}`, 'fixture'); });
    const navigation = screen.getByRole('navigation', { name: 'Workspaces' });
    const menu = within(navigation).getByText('Workspaces', { exact: true }).closest('details')!;
    fireEvent.click(menu.querySelector('summary')!);
    const openViews = within(menu).getByRole('region', { name: 'Open workspaces' });
    expect(within(openViews).getAllByRole('button')).toHaveLength(6);
    expect(within(menu).getByRole('button', { name: 'Pause ambient motion' })).toBeInTheDocument();
    expect(screen.queryByRole('complementary', { name: 'Spinal workspace anchors' })).not.toBeInTheDocument();
    const current = within(openViews).getByRole('button', { name: 'Test workspace 5' });
    current.focus();
    fireEvent.click(current);
    expect(menu).not.toHaveAttribute('open');
    expect(screen.getByRole('heading', { name: 'Test workspace 5', level: 2 })).toHaveFocus();
  });

  it('dismisses the mobile menu with Escape and returns focus to its trigger', async () => {
    viewport(320);
    await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
    const menu = within(screen.getByRole('navigation', { name: 'Workspaces' }))
      .getByText('Workspaces', { exact: true }).closest('details')!;
    const trigger = menu.querySelector('summary')!;
    fireEvent.click(trigger);
    fireEvent.keyDown(menu, { key: 'Escape' });
    expect(menu).not.toHaveAttribute('open');
    expect(trigger).toHaveFocus();
  });

  it('keeps keyboard navigation available when responsive controls are replaced', async () => {
    const resize = viewport(390);
    await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
    const navigation = screen.getByRole('navigation', { name: 'Workspaces' });
    const mobileTrigger = within(navigation).getByText('Workspaces', { exact: true }).closest('summary')!;
    mobileTrigger.focus();
    act(() => resize(1280));
    expect(within(navigation).getByRole('button', { name: 'Conversation' })).toHaveFocus();

    within(navigation).getByRole('button', { name: 'Recent observations' }).focus();
    act(() => resize(390));
    expect(within(navigation).getByRole('button', { name: 'Conversation' })).toHaveFocus();
  });

  it('hands off focus when the desktop workspace rail is removed on phone resize', async () => {
    const resize = viewport(1280);
    await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
    act(() => openWorkspacePanel('test', 'Test workspace', 'fixture'));
    const rail = screen.getByRole('complementary', { name: 'Spinal workspace anchors' });
    within(rail).getByRole('button', { name: 'Test workspace' }).focus();
    act(() => resize(390));
    expect(screen.getByRole('button', { name: 'Conversation' })).toHaveFocus();
    expect(screen.getByRole('region', { name: 'Selected workspace' })).toBeInTheDocument();
  });

  it('closes the mobile surface and category disclosures after selecting a workspace', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
      matches: query === '(max-width: 767px)' || query === '(max-width: 360px)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));

    render(<LivingWorkspaceShell experienceMode="expert" />);

    const surfaceMenu = screen.getByText('Workspaces', { exact: true }).closest('details');
    fireEvent.click(screen.getByText('Workspaces', { exact: true }));
    const taskMenu = screen.getByText('Task', { exact: true }).closest('details');
    fireEvent.click(screen.getByText('Task', { exact: true }));
    fireEvent.click(screen.getByRole('button', { name: 'Recent observations' }));

    expect(surfaceMenu).not.toHaveAttribute('open');
    expect(taskMenu).not.toHaveAttribute('open');
    expect(screen.getByRole('region', { name: 'Selected workspace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand workspace' })).toHaveFocus();
  });
});
