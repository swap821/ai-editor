import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BodySpeech from '../../superbrain/components/canvas/BodySpeech';
import GagosChrome from '../../workbench/GagosChrome';
import { fireEvent, render, screen } from '@testing-library/react';
import { publishCognition } from '../../superbrain/lib/cognitionBus';
import { __resetReplyVoiceForTests as resetReplyVoice } from '../../superbrain/lib/replyVoiceBus';
import { dispatchLivingMirrorEvent } from '../../superbrain/lib/livingMirrorRegistry';
import { useMirrorStore } from '../../superbrain/lib/mirrorStore';
import { setEmergencyStopPresentation } from '../emergencyStopPresentation';

type GlyphRequest = { text: string; finish: () => void };
type CaptionMesh = THREE.Mesh & {
  text: string;
  fillOpacity: number;
  outlineOpacity: number;
  textRenderInfo: { parameters: { text: string } } | null;
  geometry: THREE.InstancedBufferGeometry;
};
const glyphs = vi.hoisted(() => ({ requests: [] as GlyphRequest[] }));
const replyTransport = vi.hoisted(() => ({
  count: 0, chunk: null as null | ((text: string) => void),
  finish: null as null | ((text: string) => void),
}));
vi.mock('../../superbrain/lib/aiosAdapter', async original => ({
  ...await original<Record<string, unknown>>(),
  fetchOnboardingState: async () => ({ firstDirective: true, firstApproval: true,
    firstVerify: true, firstCloudRoute: false, firstAutonomy: false }),
  sendVoiceTurn: async (_text: string, options: { onChunk: (text: string) => void }) => {
    replyTransport.count++;
    if (replyTransport.count === 1) {
      options.onChunk('A completed answer stays in history.');
      return 'A completed answer stays in history.';
    }
    replyTransport.chunk = options.onChunk;
    options.onChunk('A live partial caption');
    return new Promise<string>(resolve => { replyTransport.finish = resolve; });
  },
}));

// jsdom cannot load worker fonts/SDFs. Replace that external operation only:
// use the installed Troika source Text, including its actual setters, sync queue,
// callback ordering, render info and geometry updates, through real drei Text.
// BodySpeech, Billboard, R3F, caption bus and motion preference remain real.
// This is a CPU lifecycle/geometry witness, not raster/GPU or native audio proof.
vi.mock('../../../node_modules/troika-three-text/src/TextBuilder.js', () => ({
  getTextRenderInfo(parameters: { text: string }, callback: (info: object) => void) {
    const text = parameters.text;
    glyphs.requests.push({ text, finish() {
      const count = text.length;
      const glyphBounds = new Float32Array(count * 4);
      for (let i = 0; i < count; i++) glyphBounds.set([i, 0, i + 1, 1], i * 4);
      callback(Object.freeze({
        parameters, sdfTexture: new THREE.Texture(), sdfGlyphSize: 64, sdfExponent: 9,
        glyphBounds, glyphAtlasIndices: new Float32Array(count), glyphColors: undefined,
        caretPositions: new Float32Array(), chunkedBounds: undefined,
        ascender: 1, descender: 0, lineHeight: 1, capHeight: 1, xHeight: 1, topBaseline: 1,
        blockBounds: [0, 0, count, 1], visibleBounds: [0, 0, count, 1], timings: {},
      }));
    } });
  },
}));
vi.mock('troika-three-text', async (original) => ({
  ...await original<Record<string, unknown>>(),
  ...await vi.importActual<{ Text: new () => CaptionMesh }>('../../../node_modules/troika-three-text/src/Text.js'),
  preloadFont(_parameters: object, callback: () => void) { callback(); },
}));
vi.mock('@react-three/drei', async (original) => ({
  ...await original<Record<string, unknown>>(),
  ...await vi.importActual<Record<string, unknown>>('../../../node_modules/@react-three/drei/core/Text.js'),
}));

extend({ Group: THREE.Group });
let wallMs: number;
let media: EventTarget & { matches: boolean };
beforeEach(() => {
  glyphs.requests.length = 0;
  wallMs = 10_000;
  media = Object.assign(new EventTarget(), { matches: false });
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('matchMedia', () => media);
  vi.spyOn(performance, 'now').mockImplementation(() => wallMs);
  localStorage.removeItem('gagos-pause-motion-v1');
  resetReplyVoice();
  replyTransport.count = 0; replyTransport.chunk = null; replyTransport.finish = null;
  setEmergencyStopPresentation('unknown');
  useMirrorStore.setState(useMirrorStore.getInitialState(), true);
  vi.stubGlobal('fetch', async () => new Response('No external request in this test', { status: 503 }));
});
afterEach(() => {
  resetReplyVoice();
  localStorage.removeItem('gagos-pause-motion-v1');
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

async function mountCaption() {
  const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const renderer = { domElement: canvas, render(scene: THREE.Scene) { scene.updateMatrixWorld(true); },
    setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl: renderer, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
    frameloop: 'never', size: { width: 400, height: 400, top: 0, left: 0 } });
  await act(async () => { root.render(<BodySpeech />); });
  let mesh!: CaptionMesh;
  store.getState().scene.traverse(object => {
    if (object instanceof THREE.Mesh && 'textRenderInfo' in object) mesh = object as CaptionMesh;
  });
  expect(mesh).toBeDefined();
  // Complete drei's initial empty layout; subsequent requests are controlled.
  expect(glyphs.requests[0].text).toBe('');
  act(() => glyphs.requests.shift()!.finish());
  const group = mesh.parent!;
  let time = 0;
  return { mesh, group, step(ms = 0) {
    wallMs += ms; time += 1 / 60;
    act(() => advance(time, false, store.getState()));
  }, close: () => act(async () => { root.unmount(); }) };
}
const reply = (text: string) => publishCognition({ type: 'voice-speaking', source: 'reply', data: { phase: 'reply', reply: text } });
const phase = (value: string) => publishCognition({ type: 'voice-speaking', source: 'reply', data: { phase: value } });

describe('the actual 3D caption glyph lifecycle', () => {
  // Break caught: the actual DOM caller observes global Stop but never
  // retires its reply signal. Keep real R3F/drei/Troika and only substitute
  // the external network/font operations, not the caption/Stop owners.
  it.each([false, true])('real canonical Stop reaches rendered glyphs while retaining DOM history and draft; reduced=%s', async reduced => {
    media.matches = reduced;
    const view = render(<GagosChrome integrated />);
    const caption = await mountCaption();
    const { mesh, group, step } = caption;
    const geometry = mesh.geometry;
    try {
      const input = screen.getByLabelText('Talk to GAGOS');
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Explain the first idea' } });
        fireEvent.keyDown(input, { key: 'Enter' });
      });
      step(); act(() => glyphs.requests.shift()!.finish());
      expect(mesh.textRenderInfo!.parameters.text).toBe('A completed answer stays in history.');
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Explain another idea' } });
        fireEvent.keyDown(input, { key: 'Enter' });
      });
      step(); act(() => glyphs.requests.shift()!.finish());
      expect(group.visible).toBe(true);
      expect(mesh.textRenderInfo!.parameters.text).toBe('A live partial caption');
      fireEvent.change(input, { target: { value: 'Keep this glyph bridge draft unsent' } });
      await act(async () => {
        expect(dispatchLivingMirrorEvent({ id: 1, eventType: 'governance.emergency_stop.engaged',
          canonical: { eventId: 'caption-stop-1', eventType: 'governance.emergency_stop.engaged',
            schema_version: '1', payload: { reason: 'Fixture-only stop' }, reason: 'Fixture-only stop' },
          payload: { reason: 'Fixture-only stop' } })).toBe(true);
      });
      step();
      expect(group.visible, 'actual glyph consumer must obey the observed global Stop').toBe(false);
      expect(mesh.geometry).toBe(geometry); // Hide live words; don't destroy their owner.
      expect(screen.getByRole('log', { name: 'Conversation with GAGOS' })).toHaveTextContent('A completed answer stays in history.');
      expect(input).toHaveValue('Keep this glyph bridge draft unsent');
      await act(async () => {
        replyTransport.chunk?.('An obsolete reply');
        replyTransport.finish?.('An obsolete reply');
        expect(dispatchLivingMirrorEvent({ id: 2, eventType: 'governance.emergency_stop.cleared',
          canonical: { eventId: 'caption-stop-2', eventType: 'governance.emergency_stop.cleared',
            schema_version: '1', payload: {} }, payload: {} })).toBe(true);
      });
      step();
      expect(group.visible).toBe(false);
      expect(mesh.geometry).toBe(geometry);
      expect(screen.getByRole('log', { name: 'Conversation with GAGOS' })).not.toHaveTextContent('An obsolete reply');
    } finally {
      await act(async () => { view.unmount(); });
      await caption.close();
    }
  });
  // Break caught: an older callback clears the newer request's watchdog, so a
  // stream remains permanently on old glyphs. Recovery must preserve the mesh.
  it.each([false, true])('recovers a queued stalled update after an older completion; reduced=%s', async reduced => {
    media.matches = reduced;
    const caption = await mountCaption();
    const { mesh, group, step } = caption;
    const geometry = mesh.geometry, material = mesh.material;
    try {
      reply('First words'); step();
      const older = glyphs.requests.shift()!;
      reply('First words, then the rest'); step(100);
      expect(mesh.text).toBe('First words, then the rest');
      act(() => older.finish()); // Troika starts the queued request BEFORE old callback
      const stalled = glyphs.requests.shift()!;
      expect(stalled.text).toBe('First words, then the rest');
      expect(mesh.textRenderInfo!.parameters.text).toBe('First words');
      step(1);
      expect(glyphs.requests, 'a healthy queued build keeps its original recovery interval').toHaveLength(0);
      step(1_100); // older pending interval exceeds the existing 1200ms watchdog
      expect(glyphs.requests, 'new words must not lose their stalled-build recovery').toHaveLength(1);
      act(() => glyphs.requests.shift()!.finish());
      expect(mesh.textRenderInfo!.parameters.text).toBe('First words, then the rest');
      expect(mesh.geometry.instanceCount).toBe(26);
      expect(group.visible).toBe(true);
      expect(mesh.fillOpacity).toBe(1);
      expect(mesh.outlineOpacity).toBe(0.6);
      expect(mesh.geometry).toBe(geometry);
      // Troika's outlined material getter returns a new two-element wrapper,
      // not new materials. Preserve the actual fill/outline owners.
      expect((mesh.material as THREE.Material[])[0]).toBe((material as THREE.Material[])[0]);
      expect((mesh.material as THREE.Material[])[1]).toBe((material as THREE.Material[])[1]);
      expect(group.children).toContain(mesh);
    } finally { await caption.close(); }
  });

  // Break caught: forcing a retry doesn't cancel Troika's old async request.
  // Its late geometry can overwrite a newer completed reply and must recover.
  it('repairs a late obsolete glyph completion after a successful watchdog retry', async () => {
    const caption = await mountCaption();
    const { mesh, step } = caption;
    try {
      reply('Older'); step(); const obsolete = glyphs.requests.shift()!;
      reply('Current reply'); step(1_201); const retry = glyphs.requests.shift()!;
      act(() => retry.finish());
      expect(mesh.textRenderInfo!.parameters.text).toBe('Current reply');
      act(() => obsolete.finish()); step(1);
      expect(glyphs.requests, 'obsolete glyphs must schedule repair of current text').toHaveLength(1);
      act(() => glyphs.requests.shift()!.finish());
      expect(mesh.textRenderInfo!.parameters.text).toBe('Current reply');
      expect(mesh.geometry.instanceCount).toBe(13);
    } finally { await caption.close(); }
  });

  it('gives each forced retry its recovery interval instead of restarting every frame', async () => {
    const caption = await mountCaption();
    const { mesh, step } = caption;
    try {
      reply('Current reply'); step(); const obsolete = glyphs.requests.shift()!;
      step(1_200); expect(glyphs.requests).toHaveLength(0);
      step(1); const retry = glyphs.requests.shift()!;
      expect(retry.text).toBe('Current reply');
      step(1); expect.soft(glyphs.requests, 'a fresh retry is not already stalled').toHaveLength(0);
      step(1_199); expect.soft(glyphs.requests, 'exact retry deadline does not requeue').toHaveLength(0);
      step(1); expect(glyphs.requests).toHaveLength(1);
      act(() => glyphs.requests.shift()!.finish());
      expect(mesh.textRenderInfo!.parameters.text).toBe('Current reply');
      act(() => obsolete.finish()); // preserve a genuinely uncancelled late request
    } finally { await caption.close(); }
  });

  it.each([false, true])('does not resurrect old reply glyphs for an empty error after a new question; reduced=%s', async reduced => {
    media.matches = reduced;
    const caption = await mountCaption();
    const { mesh, group, step } = caption;
    try {
      reply('Previous answer'); step(); act(() => glyphs.requests.shift()!.finish());
      phase('reply-complete'); step(); expect(group.visible).toBe(true);
      phase('question'); step(); expect(group.visible).toBe(false);
      phase('error'); step();
      expect(group.visible, 'a failure without caption text is not the previous answer').toBe(false);
      // Readable DOM history is outside this renderer. Its last glyph buffer
      // need not be deleted; it must simply not become a new error caption.
      expect(mesh.textRenderInfo!.parameters.text).toBe('Previous answer');
    } finally { await caption.close(); }
  });

  it('keeps a meaningful failed reply readable, then naturally settles it', async () => {
    const caption = await mountCaption();
    const { mesh, group, step } = caption;
    try {
      reply('Partial answer before failure'); step(); act(() => glyphs.requests.shift()!.finish());
      phase('error'); step(2_600);
      expect(group.visible).toBe(true);
      expect(mesh.textRenderInfo!.parameters.text).toBe('Partial answer before failure');
      expect(mesh.fillOpacity).toBeCloseTo(0.85, 8);
      step(1_400); expect(group.visible).toBe(false);
    } finally { await caption.close(); }
  });

  it('coalesces healthy streaming updates without unnecessary recovery or remount on a motion change', async () => {
    const caption = await mountCaption();
    const { mesh, group, step } = caption;
    const geometry = mesh.geometry;
    try {
      reply('One'); step(); const first = glyphs.requests.shift()!;
      reply('One two'); step(100);
      reply('One two three'); step(100);
      act(() => first.finish());
      expect(mesh.textRenderInfo!.parameters.text).toBe('One');
      act(() => glyphs.requests.shift()!.finish());
      expect(mesh.textRenderInfo!.parameters.text).toBe('One two three');
      expect(mesh.geometry.instanceCount).toBe(13);
      await act(async () => { media.matches = true; media.dispatchEvent(new Event('change')); });
      step(1_201);
      expect(glyphs.requests).toHaveLength(0);
      expect(group.visible).toBe(true); expect(mesh.fillOpacity).toBe(1);
      expect(mesh.geometry).toBe(geometry); expect(group.children).toContain(mesh);
      phase('speaking'); step(4_000);
      expect(group.visible).toBe(true); expect(glyphs.requests).toHaveLength(0);
      phase('speaking-complete'); step(2_600);
      expect(group.visible).toBe(true); expect(mesh.textRenderInfo!.parameters.text).toBe('One two three');
    } finally { await caption.close(); }
  });

  // Positive control: settled text is not blanket-cleared by silence, reduced
  // motion or a new layout callback. Stop is distinct from natural completion.
  it.each([false, true])('retains completed text through hold/fade, but Stop hides it immediately; reduced=%s', async reduced => {
    media.matches = reduced;
    const caption = await mountCaption();
    const { mesh, group, step } = caption;
    try {
      reply('Readable result'); step(); act(() => glyphs.requests.shift()!.finish());
      phase('reply-complete'); step(2_600);
      expect(group.visible).toBe(true);
      expect(mesh.textRenderInfo!.parameters.text).toBe('Readable result');
      expect(mesh.fillOpacity).toBeCloseTo(0.925, 8);
      step(700);
      expect(group.visible).toBe(true); expect(mesh.fillOpacity).toBeCloseTo(0.35625, 8);
      step(700); expect(group.visible).toBe(false);
      reply('A new response'); step(); act(() => glyphs.requests.shift()!.finish());
      phase('stopped'); step(); expect(group.visible).toBe(false);
      expect(mesh.textRenderInfo!.parameters.text).toBe('A new response');
      step(5_000); expect(group.visible).toBe(false);
      reply('Recovered reply'); step(); act(() => glyphs.requests.shift()!.finish());
      expect(group.visible).toBe(true); expect(mesh.fillOpacity).toBe(1);
      expect(mesh.textRenderInfo!.parameters.text).toBe('Recovered reply');
    } finally { await caption.close(); }
  });
});
