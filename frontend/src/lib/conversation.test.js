import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  clearConversationCorrection,
  correctConversationAlignment,
  restoreConversationSession,
} from './conversation';

describe('restoreConversationSession', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('restores backend history into agent UI messages and alignment state', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        alignment: { goal: 'Continue the active task', intent: 'execute' },
        activeCorrection: { revision: 3, corrections: { goal: 'Continue the active task' } },
        correctionHistory: [{ revision: 3, status: 'active' }],
        messages: [
          { role: 'user', content: [{ text: 'start the task' }] },
          { role: 'assistant', content: [{ text: 'working on it' }] },
        ],
      }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const restored = await restoreConversationSession('session-1');

    expect(restored.alignment.goal).toBe('Continue the active task');
    expect(restored.activeCorrection.revision).toBe(3);
    expect(restored.correctionHistory).toHaveLength(1);
    expect(restored.history).toHaveLength(2);
    expect(restored.messages.map(message => message.sender)).toEqual(['user', 'ai']);
    expect(restored.messages[1].text).toBe('working on it');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).sessionId).toBe('session-1');
  });

  it('fails closed on an unsuccessful restoration response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 503 })));

    await expect(restoreConversationSession('session-1')).rejects.toThrow('Server error 503');
  });

  it('applies and clears user-authored corrections', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        alignment: { goal: 'Corrected goal', correction: { active: true } },
        activeCorrection: { revision: 2 },
        correctionHistory: [{ revision: 2, status: 'active' }],
      }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const corrected = await correctConversationAlignment('session-1', { goal: 'Corrected goal' });
    await clearConversationCorrection('session-1');

    expect(corrected.alignment.goal).toBe('Corrected goal');
    expect(fetchMock.mock.calls[0][0]).toContain('/api/v1/conversation/correction');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      sessionId: 'session-1',
      corrections: { goal: 'Corrected goal' },
    });
    expect(fetchMock.mock.calls[1][0]).toContain('/api/v1/conversation/correction/clear');
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ sessionId: 'session-1' });
  });
});
