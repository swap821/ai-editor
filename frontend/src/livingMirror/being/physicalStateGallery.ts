/**
 * Development/test-only physical state gallery.
 *
 * This fixture is intentionally not imported by the product runtime. It gives
 * tests and future local inspection tools a deterministic walk through the
 * semantic presentation map at each renderer quality tier. It is not a second
 * state source and it does not model authority or execution permission.
 */

import type { QualityTier } from '../../superbrain/components/QualityTierProvider';
import type {
  BeingAttention,
  BeingCoherence,
  BeingMotion,
  BeingPhase,
  BeingPresentation,
  BeingSignal,
  HumanTaskState,
  WorkerPresentationState,
} from './semanticKernel';

export interface PhysicalStateGalleryEntry {
  readonly id: string;
  readonly label: string;
  readonly qualityTier: QualityTier;
  readonly presentation: BeingPresentation;
}

export function formatPhysicalStateGalleryAnnouncement(
  entry: PhysicalStateGalleryEntry,
  tier: QualityTier,
  reducedMotion: boolean,
): string {
  const tierLabel = tier[0].toUpperCase() + tier.slice(1);
  return `Selected ${entry.label}. Quality ${tierLabel}. ${reducedMotion ? 'Reduced motion enabled.' : 'Full motion enabled.'}`;
}

interface PresentationOverrides {
  phase?: BeingPhase;
  taskState?: HumanTaskState;
  coherence?: BeingCoherence;
  motion?: BeingMotion;
  attention?: BeingAttention;
  signals?: BeingSignal[];
  workers?: WorkerPresentationState[];
}

const presentation = (overrides: PresentationOverrides = {}): BeingPresentation => ({
  phase: 'resting',
  taskState: 'idle',
  coherence: 'fresh',
  motion: 'calm',
  attention: 'none',
  signals: [],
  workers: [],
  ...overrides,
});

const entry = (
  id: string,
  label: string,
  qualityTier: QualityTier,
  overrides: PresentationOverrides,
): PhysicalStateGalleryEntry => ({
  id,
  label,
  qualityTier,
  presentation: presentation(overrides),
});

export const PHYSICAL_STATE_GALLERY: readonly PhysicalStateGalleryEntry[] = [
  entry('booting', 'Booting / no settled task', 'low', {
    phase: 'booting',
  }),
  entry('arriving', 'Arriving into the workspace', 'medium', {
    phase: 'arriving',
    motion: 'materialize',
  }),
  entry('resting', 'Resting / ready', 'medium', {}),
  entry('listening', 'Listening to a human input', 'low', {
    phase: 'listening',
    taskState: 'understood',
    motion: 'attention',
    attention: 'human',
  }),
  entry('understanding', 'Understanding the request', 'high', {
    phase: 'understanding',
    taskState: 'understood',
    motion: 'attention',
    attention: 'human',
  }),
  entry('planning', 'Planning before action', 'medium', {
    phase: 'planning',
    taskState: 'preparing',
    motion: 'attention',
  }),
  entry('approval-hold', 'Awaiting a human boundary', 'low', {
    phase: 'awaiting-human',
    taskState: 'needs-permission',
    motion: 'attention',
    attention: 'approval',
    workers: ['awaiting-capability'],
  }),
  entry('acting', 'Conducting admitted work', 'medium', {
    phase: 'acting',
    taskState: 'working',
    motion: 'conduct',
    attention: 'workspace',
    signals: ['worker-active'],
    workers: ['active'],
  }),
  entry('verification-pending', 'Checking an unsettled result', 'low', {
    phase: 'verifying',
    taskState: 'checking',
    motion: 'verify',
    attention: 'workspace',
    workers: ['active'],
  }),
  entry('verification-pass', 'Verified result settled', 'high', {
    phase: 'resting',
    taskState: 'done-verified',
    signals: ['verification-pass'],
  }),
  entry('verification-fail', 'Failed verification moving to recovery', 'high', {
    phase: 'recovering',
    taskState: 'failed',
    coherence: 'degraded',
    motion: 'reabsorb',
    signals: ['verification-fail'],
    workers: ['failed'],
  }),
  entry('unverified', 'Finished but not verified', 'medium', {
    phase: 'resting',
    taskState: 'done-unverified',
    coherence: 'unverified',
  }),
  entry('learning', 'Promoting a durable lesson', 'medium', {
    phase: 'learning',
    taskState: 'working',
    motion: 'attention',
    attention: 'workspace',
    signals: ['memory-promoted', 'curriculum-mastered'],
  }),
  entry('memory-recall', 'Reconnecting recalled context', 'low', {
    phase: 'understanding',
    taskState: 'understood',
    motion: 'attention',
    attention: 'workspace',
    signals: ['memory-recalled'],
  }),
  entry('reflex', 'Reusing a verified reflex', 'high', {
    phase: 'reflex',
    taskState: 'working',
    motion: 'conduct',
    attention: 'workspace',
    signals: ['reflex-reused'],
    workers: ['active'],
  }),
  entry('refusal', 'Refused or injection-blocked action', 'medium', {
    phase: 'recovering',
    taskState: 'refused',
    motion: 'refuse',
    signals: ['refusal', 'injection-blocked'],
    workers: ['failed'],
  }),
  entry('rollback-recovering', 'Rollback / reabsorption', 'medium', {
    phase: 'recovering',
    taskState: 'restored',
    coherence: 'degraded',
    motion: 'reabsorb',
    signals: ['rollback'],
    workers: ['returned'],
  }),
  entry('stale', 'Stale mirror snapshot', 'low', {
    phase: 'stale',
    taskState: 'stale',
    coherence: 'stale',
  }),
  entry('degraded', 'Degraded / unavailable mirror', 'high', {
    phase: 'degraded',
    coherence: 'degraded',
  }),
  entry('stopped', 'Emergency stop engaged', 'low', {
    phase: 'stopped',
    taskState: 'stopped',
    coherence: 'stopped',
    motion: 'stop',
    signals: ['emergency-stop'],
    workers: ['active'],
  }),
  entry('worker-burst', 'Bounded worker burst with terminal receipts', 'high', {
    phase: 'acting',
    taskState: 'working',
    motion: 'conduct',
    attention: 'workspace',
    workers: [
      'requested',
      'admitted',
      'active',
      'awaiting-capability',
      'returned',
      'dissolved',
      'failed',
      'killed',
      'active',
    ],
  }),
];
