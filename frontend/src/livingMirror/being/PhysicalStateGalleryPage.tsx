import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import CortexEngine from '../../superbrain/core/CortexEngine';
import { QualityTierProvider, type QualityTier } from '../../superbrain/components/QualityTierProvider';
import { getReducedMotionSnapshot, setAmbientMotionPaused } from '../../superbrain/lib/reducedMotion';
import SuperbrainReactiveEffects from '../../workbench/SuperbrainReactiveEffects';
import { derivePhysicalSnapshot } from './physicalSnapshot';
import {
  formatPhysicalStateGalleryAnnouncement,
  PHYSICAL_STATE_GALLERY,
  type PhysicalStateGalleryEntry,
} from './physicalStateGallery';
import './PhysicalStateGalleryPage.css';

const QUALITY_TIERS: readonly QualityTier[] = ['low', 'medium', 'high'];

function GalleryScene({ entry, tier }: { entry: PhysicalStateGalleryEntry; tier: QualityTier }) {
  return (
    <QualityTierProvider key={tier} defaultTier={tier}>
      <Canvas
        camera={{ position: [0, 0.25, 8.5], fov: 42, near: 0.1, far: 150 }}
        dpr={tier === 'high' ? 1 : tier === 'medium' ? 0.85 : 0.7}
        gl={{ antialias: false, alpha: false, powerPreference: 'high-performance' }}
      >
        <color attach="background" args={['#000000']} />
        <fog attach="fog" args={['#000000', 50, 150]} />
        <Suspense fallback={null}>
          <CortexEngine mode="orchestrate" activity={0.72} tier={tier} sky="voyage" surface="web" />
          <SuperbrainReactiveEffects presentationOverride={entry.presentation} />
        </Suspense>
      </Canvas>
    </QualityTierProvider>
  );
}

function tierLabel(tier: QualityTier): string {
  return tier[0].toUpperCase() + tier.slice(1);
}

/**
 * Development-only visual acceptance gallery. It is intentionally reachable
 * only from the Vite dev entry (`?physical-gallery=1`), consumes deterministic
 * presentation fixtures, and uses the same CortexEngine/reactive seam as the
 * product. It never writes mirror/tab state or represents backend evidence.
 */
export default function PhysicalStateGalleryPage() {
  const initialPause = useRef<string | null>(
    typeof window === 'undefined' ? null : window.localStorage.getItem('gagos-pause-motion-v1'),
  );
  const [selectedId, setSelectedId] = useState('resting');
  const selected = useMemo(
    () => PHYSICAL_STATE_GALLERY.find((entry) => entry.id === selectedId) ?? PHYSICAL_STATE_GALLERY[0],
    [selectedId],
  );
  const [tier, setTier] = useState<QualityTier>(selected.qualityTier);
  const [reducedMotion, setReducedMotion] = useState(() => getReducedMotionSnapshot());
  const physical = useMemo(() => derivePhysicalSnapshot(selected.presentation), [selected]);
  const announcement = useMemo(
    () => formatPhysicalStateGalleryAnnouncement(selected, tier, reducedMotion),
    [reducedMotion, selected, tier],
  );

  useEffect(() => {
    setAmbientMotionPaused(reducedMotion);
  }, [reducedMotion]);

  useEffect(() => () => {
    if (initialPause.current === null) {
      try { window.localStorage.removeItem('gagos-pause-motion-v1'); } catch { /* preference unavailable */ }
      window.dispatchEvent(new Event('gagos:motion-preference'));
      return;
    }
    try { window.localStorage.setItem('gagos-pause-motion-v1', initialPause.current); } catch { /* preference unavailable */ }
    window.dispatchEvent(new Event('gagos:motion-preference'));
  }, []);

  return (
    <main className="physical-gallery" data-testid="physical-gallery" data-state={selected.id}>
      <header className="physical-gallery__header">
        <div>
          <p className="physical-gallery__eyebrow">Development inspection · physical projection only</p>
          <h1>GAGOS physical state gallery</h1>
          <p className="physical-gallery__lede">Deterministic fixtures rendered through the live CortexEngine and product-owned reactive seam.</p>
        </div>
        <div className="physical-gallery__controls" aria-label="Gallery controls">
          <label>
            Quality
            <select value={tier} onChange={(event) => setTier(event.target.value as QualityTier)}>
              {QUALITY_TIERS.map((option) => <option key={option} value={option}>{tierLabel(option)}</option>)}
            </select>
          </label>
          <label className="physical-gallery__toggle">
            <input type="checkbox" checked={reducedMotion} onChange={(event) => setReducedMotion(event.target.checked)} />
            Reduced motion
          </label>
        </div>
      </header>
      <p className="physical-gallery__announcement" role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </p>

      <section className="physical-gallery__workspace" aria-label="Selected physical state">
        <div className="physical-gallery__canvas"><GalleryScene entry={selected} tier={tier} /></div>
        <aside className="physical-gallery__inspector">
          <p className="physical-gallery__eyebrow">Selected fixture</p>
          <h2>{selected.label}</h2>
          <p className="physical-gallery__code">{selected.id} · {tierLabel(tier)}{reducedMotion ? ' · reduced motion' : ''}</p>
          <dl>
            <div><dt>Cortex</dt><dd>{physical.cortex.posture} · convergence {physical.cortex.convergence}</dd></div>
            <div><dt>Conductor</dt><dd>{physical.conductor.posture} · {physical.conductor.travel}</dd></div>
            <div><dt>Branches</dt><dd>{physical.branches.length} bounded</dd></div>
            <div><dt>Memory</dt><dd>{physical.memory.layer}</dd></div>
            <div><dt>Verification</dt><dd>{physical.verification.state} · {physical.verification.settlement}</dd></div>
            <div><dt>Membrane</dt><dd>{physical.membrane.state}</dd></div>
          </dl>
        </aside>
      </section>

      <nav className="physical-gallery__fixtures" aria-label="Physical state fixtures">
        {PHYSICAL_STATE_GALLERY.map((entry) => (
          <button
            key={entry.id}
            type="button"
            className={entry.id === selected.id ? 'is-selected' : ''}
            aria-pressed={entry.id === selected.id}
            onClick={() => {
              setSelectedId(entry.id);
              setTier(entry.qualityTier);
            }}
          >
            <span>{entry.label}</span>
            <small>{entry.id} · {tierLabel(entry.qualityTier)}</small>
          </button>
        ))}
      </nav>
    </main>
  );
}
