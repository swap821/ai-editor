// Singleton store: the being's current spoken reply, read off the SAME voice-speaking
// cognition events the chat already publishes (GagosChrome). SSR-safe; mirrors the
// conversationPhaseBus pattern. The point scene polls getReplyVoice() each frame.
import { subscribeCognition } from './cognitionBus';
import type { BodySpeechPhase } from './bodySpeech';

interface ReplyVoiceState { phase: BodySpeechPhase; text: string; since: number; }
let state: ReplyVoiceState = { phase: 'idle', text: '', since: 0 };
const listeners = new Set<() => void>();

function nowMs(): number {
  return typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now();
}
function set(next: ReplyVoiceState): void {
  state = next;
  for (const l of listeners) { try { l(); } catch { /* one bad listener never breaks the rest */ } }
}
function ingest(event: { type: string; source?: string; data?: { phase?: string; reply?: string; text?: string } }): void {
  if (event.type !== 'voice-speaking') return;
  const p = event.data?.phase ?? '';
  if (p === 'question') { set({ phase: 'idle', text: '', since: nowMs() }); return; }
  if (p === 'reply') { set({ phase: 'streaming', text: String(event.data?.reply ?? ''), since: nowMs() }); return; }
  if (p === 'reply-complete') { set({ phase: 'complete', text: state.text, since: nowMs() }); return; }
  // Slice 2 TTS loop: the being keeps glowing while the reply is spoken aloud.
  if (p === 'speaking') { set({ phase: 'streaming', text: String(event.data?.reply ?? state.text), since: nowMs() }); return; }
  if (p === 'speaking-complete') { set({ phase: 'complete', text: state.text, since: nowMs() }); return; }
  if (p === 'error') { set({ phase: 'error', text: state.text, since: nowMs() }); }
}

export function getReplyVoice(): ReplyVoiceState { return state; }
export function subscribeReplyVoice(l: () => void): () => void { listeners.add(l); return () => { listeners.delete(l); }; }

if (typeof window !== 'undefined') {
  subscribeCognition((e) => ingest(e as Parameters<typeof ingest>[0]));
  (window as unknown as { __getBodySpeech?: () => ReplyVoiceState }).__getBodySpeech = () => state;
}

export function __ingestVoiceForTests(e: Parameters<typeof ingest>[0]): void { ingest(e); }
export function __resetReplyVoiceForTests(): void { state = { phase: 'idle', text: '', since: 0 }; listeners.clear(); }
