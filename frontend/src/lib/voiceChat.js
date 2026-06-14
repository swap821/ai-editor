import { API_BASE, API_HEADERS } from '../config';
import { parseSseBuffer } from './sse';

/**
 * streamChatReply — stream one conversational reply from the Jarvis voice mind
 * (POST /api/v1/chat, SSE).
 *
 * CARDINAL RULE (voice is a DIRECTIVE/conversation channel, never consent): this
 * endpoint runs NO tools and has NO approval mechanism, so a spoken word can
 * never redeem an approval token — a spoken "yes" cannot authorize anything. The
 * agentic forge (approvals, file writes) stays on the typed `/api/generate` path.
 *
 * `onChunk(replySoFar)` is invoked as the reply streams (for live captioning).
 * Resolves with the full reply text, or throws on a transport / backend error
 * (the caller surfaces that honestly and never fabricates a reply).
 *
 * @param {string} transcript  the operator's spoken/typed turn
 * @param {string} sessionId   the shared aios_session_id (one conversation)
 * @param {{ onChunk?: (reply: string) => void, signal?: AbortSignal }} [opts]
 * @returns {Promise<string>}  the full reply
 */
export async function streamChatReply(transcript, sessionId, opts = {}) {
  const { onChunk, signal } = opts;
  const res = await fetch(`${API_BASE}/api/v1/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify({ transcript, sessionId }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`chat backend responded ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let reply = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { frames, rest } = parseSseBuffer(buffer);
    buffer = rest;
    for (const frame of frames) {
      if (frame.event === 'text_chunk') {
        // Malformed frames are skipped, never thrown — one bad frame must not
        // abort a streaming reply.
        try {
          reply += JSON.parse(frame.data).text ?? '';
          onChunk?.(reply);
        } catch {
          /* ignore a malformed text_chunk */
        }
      } else if (frame.event === 'error') {
        let detail = 'The voice mind could not answer.';
        try {
          detail = JSON.parse(frame.data).text ?? detail;
        } catch {
          /* keep the default */
        }
        throw new Error(detail);
      }
      // 'route' / 'done' carry no reply text for this lean conversational path.
    }
  }
  return reply;
}
