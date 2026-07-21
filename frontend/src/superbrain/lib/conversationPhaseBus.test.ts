import { describe, it, expect, beforeEach } from 'vitest';
import {
  effectiveConversationPhase,
  conversationToOrganismPhase,
  getConversationPhase,
  setConversationPhase,
  getEffectiveOrganismPhase,
  COMPLETE_HOLD_MS,
  ERROR_HOLD_MS,
  __resetConversationPhaseForTests,
} from './conversationPhaseBus';
import { setOrganismPhase } from './organismPhaseBus';

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

describe('getEffectiveOrganismPhase (single source for the conversation-priority override)', () => {
  beforeEach(() => {
    __resetConversationPhaseForTests();
    setOrganismPhase('rest');
  });

  // Regression: a plain CHAT turn (no materialized work surface) never moves the
  // organism-lifecycle phase off 'rest' — only conversationPhaseBus reflects it.
  // Every scene-level visual that reacts to "the being is mid-turn" (body posture
  // AND the intake command-nerve) MUST read the conversation-aware phase, or it
  // silently ignores the entire chat turn. This single helper is the one place
  // that override happens, so a new consumer can't forget it the way the intake
  // nerve did (SuperbrainScene previously called intakeNerveDrive(getOrganismPhase())
  // directly, bypassing the override entirely).
  it('prioritizes the conversation phase over the idle organism phase during a chat turn', () => {
    expect(getEffectiveOrganismPhase()).toBe('rest');
    setConversationPhase('streaming');
    expect(getEffectiveOrganismPhase()).toBe('working');
  });

  it('falls back to the organism phase once the conversation goes idle', () => {
    setConversationPhase('streaming');
    expect(getEffectiveOrganismPhase()).toBe('working');
    setConversationPhase('idle');
    expect(getEffectiveOrganismPhase()).toBe('rest');
  });

  it('still lets real work-surface organism phases through when the conversation is idle', () => {
    setOrganismPhase('materializing');
    expect(getEffectiveOrganismPhase()).toBe('materializing');
  });
});
