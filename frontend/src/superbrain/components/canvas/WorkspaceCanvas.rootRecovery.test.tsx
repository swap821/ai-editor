import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { WebGLRenderer } from 'three';
import FixtureJourneyPage from '../../../livingMirror/being/FixtureJourneyPage';
import { createFixtureJourneyTransport } from '../../../livingMirror/being/fixtureJourneyTransport';
import { __resetAiosAdapterForTests, getPendingApproval } from '../../lib/aiosAdapter';
import { __resetTabStoreForTests, getTabStoreSnapshot } from '../../lib/tabStore';
import { useMirrorStore } from '../../lib/mirrorStore';
import { setConversationPhase } from '../../lib/conversationPhaseBus';
import { EXPERIENCE_MODE_STORAGE_KEY } from '../../../livingMirror/experienceMode';

// Only rendering/background graphics polling are external doubles. The app,
// quality owner, conversation, transport admission, permission and work stay real.
const driver = vi.hoisted(() => ({ renderers: [] as WebGLRenderer[], failRender: false }));
vi.mock('@react-three/fiber', async () => {
  const React = await import('react');
  return {
    Canvas: ({ children, onCreated }: { children: ReactNode; onCreated: (state: { gl: WebGLRenderer }) => void }) => {
      if (driver.failRender) throw new Error('controlled root graphics failure');
      const canvas = React.useRef<HTMLCanvasElement>(null);
      React.useLayoutEffect(() => {
        const gl = { domElement: canvas.current, capabilities: { isWebGL2: true }, debug: { checkShaderErrors: true, onShaderError: null } } as unknown as WebGLRenderer;
        driver.renderers.push(gl); onCreated({ gl });
      }, []);
      const content = React.Children.toArray(children).filter(child => !React.isValidElement(child) || !['color', 'fog'].includes(String(child.type)));
      return <div><canvas ref={canvas} />{content}</div>;
    },
    useFrame: () => {},
  };
});
vi.mock('../../core/CortexEngine', () => ({ default: () => null }));
vi.mock('./TierGovernor', () => ({ default: () => null }));
vi.mock('./RenderFrameLoop', () => ({ default: () => null }));
vi.mock('../../../workbench/SuperbrainReactiveEffects', () => ({ default: () => null }));
vi.mock('../../../livingMirror/being/WorkspaceConnectionProjection', () => ({ WorkspaceConnectionProjection: () => null }));
vi.mock('../../../livingMirror/being/WorkspaceThumbnailTargets', () => ({ WorkspaceThumbnailTargets: () => null }));
// The graphics-fault harness does not load the GLB or mount the real scene.
vi.mock('@/components/canvas/SuperbrainScene.LEGACY', () => ({ SCENE_UNIFORMS: { uBreath: { value: 0.5 } } }));
vi.mock('@/components/ui/BootSequence', () => ({ default: () => null }));
vi.mock('../../lib/aiosAdapter', async importOriginal => ({
  ...await importOriginal<typeof import('../../lib/aiosAdapter')>(),
  startAiosPolling: () => () => {},
}));

let fixture: ReturnType<typeof createFixtureJourneyTransport>;
const previousMode = localStorage.getItem(EXPERIENCE_MODE_STORAGE_KEY);
beforeEach(() => {
  driver.renderers.length = 0; driver.failRender = false;
  __resetAiosAdapterForTests(); __resetTabStoreForTests(); setConversationPhase('idle');
  useMirrorStore.setState(useMirrorStore.getInitialState(), true);
  localStorage.setItem(EXPERIENCE_MODE_STORAGE_KEY, 'beginner');
  vi.stubGlobal('matchMedia', (query: string) => Object.assign(new EventTarget(), { matches: false, media: query, addListener() {}, removeListener() {} }));
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as WebGLRenderingContext);
  fixture = createFixtureJourneyTransport({ origin: window.location.origin, assetFetch: vi.fn<typeof fetch>() });
  vi.stubGlobal('fetch', fixture.fetch); vi.stubGlobal('EventSource', fixture.EventSource);
});
afterEach(() => {
  cleanup(); fixture?.dispose(); __resetAiosAdapterForTests(); __resetTabStoreForTests();
  useMirrorStore.setState(useMirrorStore.getInitialState(), true); setConversationPhase('idle');
  vi.unstubAllGlobals(); vi.restoreAllMocks();
  if (previousMode === null) localStorage.removeItem(EXPERIENCE_MODE_STORAGE_KEY);
  else localStorage.setItem(EXPERIENCE_MODE_STORAGE_KEY, previousMode);
});

async function advance() {
  const panel = within(screen.getByRole('complementary', { name: 'Isolated development journey' }));
  await waitFor(() => expect(panel.getByRole('button', { name: 'Advance fixture' })).toBeEnabled());
  fireEvent.click(panel.getByRole('button', { name: 'Advance fixture' }));
  await act(async () => {});
}

it.each(['shader', 'react'] as const)('keeps actual permission, draft and work owners through %s failure and root Retry', async failure => {
  const app = render(<FixtureJourneyPage fixture={fixture} />);
  await waitFor(() => expect(useMirrorStore.getState().projection).toBe('fresh'));
  await waitFor(() => expect(driver.renderers.length).toBeGreaterThan(0));
  const input = screen.getByRole<HTMLInputElement>('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(input, { target: { value: 'Create a greeting example' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  await waitFor(() => expect(fixture.getSnapshot().pending).toBe(true));
  await advance();
  fireEvent.change(input, { target: { value: 'Keep this draft through graphics recovery' } });
  await advance();
  const permission = await screen.findByRole('alertdialog', { name: 'GAGOS permission request' });
  const reader = screen.getByRole('region', { name: 'Selected workspace' });
  const approval = getPendingApproval();
  expect(approval).not.toBeNull();
  const tabId = getTabStoreSnapshot().focusId;
  const partial = within(reader).getByText('# Fixture preview — no file has been written');
  const stop = screen.getByRole('button', { name: 'Emergency stop' });
  const gl = driver.renderers[driver.renderers.length - 1];
  if (failure === 'shader') {
    const notify = gl.debug.onShaderError;
    expect(notify).toBeTypeOf('function');
    type Args = Parameters<NonNullable<typeof notify>>;
    act(() => notify!({} as Args[0], {} as Args[1], {} as Args[2], {} as Args[3]));
  } else {
    driver.failRender = true; app.rerender(<FixtureJourneyPage fixture={fixture} />);
  }
  const retry = await screen.findByRole('button', { name: 'Retry visual organism' });
  expect(screen.getByRole('alertdialog', { name: 'GAGOS permission request' })).toBe(permission);
  expect(getPendingApproval()).toBe(approval);
  expect(screen.getByRole('region', { name: 'Selected workspace' })).toBe(reader);
  expect(partial).toBeInTheDocument(); expect(input.value).toBe('Keep this draft through graphics recovery');
  expect(screen.getByRole('button', { name: 'Emergency stop' })).toBe(stop);
  driver.failRender = false;
  const rendererCount = driver.renderers.length;
  fireEvent.click(retry);
  await waitFor(() => expect(driver.renderers.length).toBe(rendererCount + 1));
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Retry visual organism' })).not.toBeInTheDocument());
  expect(getPendingApproval()).toBe(approval);
  expect(getTabStoreSnapshot().focusId).toBe(tabId);
  expect(fixture.getSnapshot()).toMatchObject({ pending: false, waitingForDecision: true });
  expect(screen.getByRole('region', { name: 'Selected workspace' })).toBe(reader);
  expect(partial).toBeInTheDocument(); expect(input.value).toBe('Keep this draft through graphics recovery');
  fireEvent.click(within(permission).getByRole('button', { name: "Don't allow" }));
  await waitFor(() => expect(getPendingApproval()).toBeNull());
  expect(fixture.getSnapshot().waitingForDecision).toBe(false);
  expect(input.value).toBe('Keep this draft through graphics recovery');
});
