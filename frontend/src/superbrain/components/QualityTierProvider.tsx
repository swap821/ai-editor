'use client';

/**
 * QualityTierProvider — the organism's metabolic governor.
 *
 * The effective tier every consumer obeys is composed from two signals:
 *
 *   baseTier   what this machine has PROVEN it can sustain. Starts from the
 *              persisted verdict in localStorage (default 'high'), and is
 *              demoted — never auto-promoted — by the in-canvas TierGovernor
 *              when measured frame rate declines. A demotion is evidence; it
 *              sticks across sessions until the operator overrides it.
 *
 *   generating the AI-OS is mid-turn (between a 'directive' and the next
 *              'synthesis'/'approval-required' on the cognition bus). While
 *              the local model is thinking it owns the machine's memory
 *              bandwidth, so the interface dims its own cortex by one tier
 *              for the duration — the product-aware degrade no generic demo
 *              can have.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { subscribeCognition } from '@/lib/cognitionBus';

export type QualityTier = 'low' | 'medium' | 'high';

/** v3: FIDELITY IS SACRED (the operator's law — see VISION.md). Only the
 *  operator's own click is ever stored here; the governor lost its write
 *  access entirely (it advises in the terminal, never acts). All earlier
 *  keys held machine-written verdicts — removed on load. */
const STORAGE_KEY = 'gag-quality-tier-v3';
const LEGACY_STORAGE_KEYS = ['gag-quality-tier', 'gag-quality-tier-v2'];
const TIERS: readonly QualityTier[] = ['low', 'medium', 'high'];

export function isQualityTier(value: unknown): value is QualityTier {
  return typeof value === 'string' && (TIERS as readonly string[]).includes(value);
}

/** One step down; 'low' is the floor. */
export function demoteTier(tier: QualityTier): QualityTier {
  return tier === 'high' ? 'medium' : 'low';
}

/** The tier consumers obey: the proven base, dimmed while the model thinks. */
export function effectiveTier(base: QualityTier, generating: boolean): QualityTier {
  return generating ? demoteTier(base) : base;
}

function readStoredTier(): QualityTier | null {
  if (typeof window === 'undefined') return null;
  try {
    for (const legacy of LEGACY_STORAGE_KEYS) {
      window.localStorage.removeItem(legacy);
    }
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isQualityTier(stored) ? stored : null;
  } catch {
    return null;
  }
}

interface QualityTierContextValue {
  /** STRUCTURAL tier: governs geometry — shells, web octaves, particle
   *  counts, the sky. Changes only with the machine's proven capability,
   *  never mid-conversation: the look must not be amputated while the
   *  operator watches. */
  tier: QualityTier;
  /** PERF tier: governs continuous costs (dpr, post-FX extras). Drops one
   *  step while the model is generating — resolution breathes, geometry
   *  stays. */
  perfTier: QualityTier;
  /** The machine's proven capability (persisted; demote-only ratchet). */
  baseTier: QualityTier;
  /** True while a real AI-OS turn is streaming. */
  generating: boolean;
  /** Operator/governor override of the base tier; persisted. */
  setTier: (tier: QualityTier) => void;
}

const QualityTierContext = createContext<QualityTierContextValue>({
  tier: 'high',
  perfTier: 'high',
  baseTier: 'high',
  generating: false,
  setTier: () => {},
});

export function useQualityTier() {
  return useContext(QualityTierContext);
}

export function QualityTierProvider({
  children,
  defaultTier = 'high',
}: {
  children: React.ReactNode;
  defaultTier?: QualityTier;
}) {
  const [baseTier, setBaseTier] = useState<QualityTier>(
    () => readStoredTier() ?? defaultTier,
  );
  const [generating, setGenerating] = useState(false);

  const setTier = useCallback((tier: QualityTier) => {
    if (!isQualityTier(tier)) return;
    setBaseTier(tier);
    try {
      window.localStorage.setItem(STORAGE_KEY, tier);
    } catch {
      // Private mode etc. — the session still gets the right tier.
    }
  }, []);

  // The product signal: dim while the AI-OS is mid-turn. 'directive' opens a
  // turn; ANY settling event — a synthesis (including the adapter's honest
  // LINK OFFLINE) or an approval hold — closes it.
  useEffect(() => {
    return subscribeCognition((event) => {
      if (event.type === 'directive') setGenerating(true);
      else if (event.type === 'synthesis' || event.type === 'approval-required') {
        setGenerating(false);
      }
    });
  }, []);

  const value = useMemo(
    () => ({
      // FIDELITY IS SACRED: the operator's chosen tier is THE tier — for
      // structure AND continuous costs alike. Nothing automatic dims it;
      // `generating` is pure status (the HUD shows '· thinking').
      tier: baseTier,
      perfTier: baseTier,
      baseTier,
      generating,
      setTier,
    }),
    [baseTier, generating, setTier],
  );

  return (
    <QualityTierContext.Provider value={value}>
      {children}
    </QualityTierContext.Provider>
  );
}
