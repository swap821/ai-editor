import { describe, it, expect, beforeEach } from 'vitest';
import {
  effectiveConversationPhase,
  conversationToOrganismPhase,
  getConversationPhase,
  setConversationPhase,
  COMPLETE_HOLD_MS,
  ERROR_HOLD_MS,
  __resetConversationPhaseForTests,
} from './conversationPhaseBus';

describe('effectiveConversationPhase (lazy decay)', () => {
  it('keeps active beats regardless of age', () => {
    expect(effectiveConversationPhase({ phase: 'thinking', since: 0 }, 999_999)).toBe('thinking');
    expect(effectiveConversationPhase({ phase: 'streaming', since: 0 }, 999_999)).toBe('streaming');
  });
  it('decays complete → idle after the hold', () => {
    expect(effectiveConversationPhase({ phase: 'complete', since: 0 }, COMPLETE_HOLD_MS - 1)).toBe('complete');
    expect(effectiveConversationPhase({ phase: 'complete', since: 0 }, COMPLETE_HOLD_MS + 1)).toBe('idle');
  });
  it('decays error → idle after the (longer) hold', () => {
    expect(effectiveConversationPhase({ phase: 'error', since: 0 }, ERROR_HOLD_MS - 1)).toBe('error');
    expect(effectiveConversationPhase({ phase: 'error', since: 0 }, ERROR_HOLD_MS + 1)).toBe('idle');
  });
});

describe('conversationToOrganismPhase', () => {
  it('maps each conversational beat to the posture-carrying organism phase', () => {
    expect(conversationToOrganismPhase('awakening')).toBe('attentive');
    expect(conversationToOrganismPhase('thinking')).toBe('attentive');
    expect(conversationToOrganismPhase('streaming')).toBe('working');
    expect(conversationToOrganismPhase('complete')).toBe('completion_settle');
    expect(conversationToOrganismPhase('error')).toBe('error_repair');
  });
  it('returns null for idle (fall back to the organism phase)', () => {
    expect(conversationToOrganismPhase('idle')).toBeNull();
  });
});

describe('conversation phase store', () => {
  beforeEach(() => __resetConversationPhaseForTests());
  it('starts idle and reflects the set beat', () => {
    expect(getConversationPhase()).toBe('idle');
    setConversationPhase('thinking');
    expect(getConversationPhase()).toBe('thinking');
  });
});
