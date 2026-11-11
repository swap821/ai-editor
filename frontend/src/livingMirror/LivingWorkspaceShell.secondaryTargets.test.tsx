import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { LivingWorkspaceShell } from './LivingWorkspaceShell';
import { __resetTabStoreForTests, focusWorkspace, getTabStoreSnapshot, setMaterializedTabLifecycle, showContentSurface, updateMaterializedTab } from '../superbrain/lib/tabStore';
import { getContentSurfacePlacement } from '../superbrain/lib/materializedSurfaceAnchors';

beforeEach(() => {
  __resetTabStoreForTests();
  vi.stubGlobal('fetch', vi.fn(async () => ({ok:false,status:503,json:async()=>({})})));
});
afterEach(() => { cleanup(); __resetTabStoreForTests(); vi.unstubAllGlobals(); });

it('binds secondary controls to live workspace identities while retaining the selected reader', async () => {
  await act(async()=>{render(<LivingWorkspaceShell experienceMode="beginner"/>);});
  let focused='',other='';
  act(()=>{
    focused=showContentSurface({filepath:'first.txt',language:'text',code:'first'},getContentSurfacePlacement(2)).id;
    setMaterializedTabLifecycle(focused,'live');
    other=showContentSurface({filepath:'second.txt',language:'text',code:'second'},getContentSurfacePlacement(4)).id;
    setMaterializedTabLifecycle(other,'live');focusWorkspace(focused);
  });
  const button=document.querySelector<HTMLButtonElement>('[data-secondary-id]');
  expect(button).not.toBeNull();expect(button!.dataset.secondaryId).toBe(other);
  // The renderer reveals it only once the matching actual surface is positioned.
  expect(button).toHaveStyle({visibility:'hidden'});
  expect(button).toHaveAttribute('aria-label','View second.txt · Anchor 4');
  button!.style.visibility='visible';
  expect(button).toHaveAccessibleName('View second.txt · Anchor 4');
  fireEvent.click(button!);
  expect(getTabStoreSnapshot().focusId).toBe(other);
  expect(screen.getByRole('heading',{name:'second.txt'})).toHaveFocus();
});

it('makes every admitted waiting workspace available to the scene, not just the first two', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="beginner"/>); });
  const ids: string[] = [];
  act(() => {
    for (let seat = 0; seat < 12; seat++) {
      const tab = showContentSurface({ filepath: `workspace-${seat}.txt`, language: 'text', code: `work ${seat}` }, getContentSurfacePlacement(seat));
      ids.push(tab.id);
      setMaterializedTabLifecycle(tab.id, 'live');
    }
    focusWorkspace(ids[0]);
  });
  const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>('[data-secondary-id]'));
  expect(buttons.map(button => button.dataset.secondaryId)).toEqual(ids.slice(1));
  const last = buttons.find(button => button.dataset.secondaryId === ids[11])!;
  expect(last).toHaveAttribute('aria-label', 'View workspace-11.txt · Anchor 11');
  last.style.visibility = 'visible';
  fireEvent.click(last);
  expect(getTabStoreSnapshot().focusId).toBe(ids[11]);
  expect(screen.getByRole('heading', { name: 'workspace-11.txt' })).toHaveFocus();
});


it('distinguishes same-named direct workspaces by their existing anchors and selects the intended one', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="beginner" />); });
  const ids: string[] = [];
  act(() => {
    for (const seat of [2, 4, 6]) {
      const tab = showContentSurface({ filepath: `initial-${seat}.txt`, language: 'text', code: `work ${seat}` }, getContentSurfacePlacement(seat));
      ids.push(tab.id);
      setMaterializedTabLifecycle(tab.id, 'live');
      updateMaterializedTab(tab.id, { content: { filepath: 'same.txt', language: 'text', code: `work ${seat}` } });
    }
    focusWorkspace(ids[0]);
  });
  const waiting = Array.from(document.querySelectorAll<HTMLButtonElement>('[data-secondary-id]'));
  expect(waiting.map(button => button.getAttribute('aria-label'))).toEqual([
    'View same.txt · Anchor 4', 'View same.txt · Anchor 6',
  ]);
  expect(waiting.map(button => button.textContent)).toEqual(['#4 · same.txt', '#6 · same.txt']);
  waiting[1].style.visibility = 'visible';
  fireEvent.click(waiting[1]);
  expect(getTabStoreSnapshot().focusId).toBe(ids[2]);
  expect(screen.getByText('work 6')).toBeVisible();
});
