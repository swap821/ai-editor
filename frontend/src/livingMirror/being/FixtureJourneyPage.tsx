import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import SuperbrainApp from '../../superbrain/SuperbrainApp';
import type { createFixtureJourneyTransport, FixtureOutcome } from './fixtureJourneyTransport';
import './FixtureJourneyPage.css';

export default function FixtureJourneyPage({ fixture }: { fixture: ReturnType<typeof createFixtureJourneyTransport> }) {
  const state = useSyncExternalStore(fixture.subscribe, fixture.getSnapshot);
  const [visualCheck, setVisualCheck] = useState('');
  const appViewportRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Typing in this deliberately inset/scrolling development app can leave
    // the body/Stop above its scrollport. Expose a newly admitted decision
    // immediately; do not reset the retained reader or later user scrolling.
    if (state.waitingForDecision && appViewportRef.current) appViewportRef.current.scrollTop = 0;
  }, [state.waitingForDecision]);
  const loseVisual = () => {
    const canvas = document.querySelector('.scene-layer canvas');
    const context = canvas instanceof HTMLCanvasElement ? canvas.getContext('webgl2') : null;
    const extension = context?.getExtension('WEBGL_lose_context');
    if (!extension) { setVisualCheck('Context-loss fixture unavailable. No visual failure was simulated.'); return; }
    setVisualCheck('Context-loss fixture requested.');
    extension.loseContext();
  };
  return <div className="fixture-journey">
    <aside className="fixture-journey__controls" aria-label="Isolated development journey">
      <div className="fixture-journey__identity">
        <strong>Fixture—not backend work</strong>
        <span>No real files, permissions or checks.</span>
        <span>Frontend candidate—not release accepted.</span>
      </div>
      <label>Outcome
        <select aria-label="Fixture outcome" value={state.outcome} disabled={state.pending || state.waitingForDecision}
          onChange={(event) => fixture.setOutcome(event.target.value as FixtureOutcome)}>
          <option value="unverified">Finished, not verified</option>
          <option value="verified">Fixture pass</option>
          <option value="failed">Fixture failure</option>
        </select>
      </label>
      <button type="button" disabled={!state.pending || state.observedStop} onClick={fixture.advance}>Advance fixture</button>
      <button type="button" onClick={loseVisual}>Simulate visual loss</button>
      <button type="button" title="Fixture observation only. No real Stop/Clear command."
        onClick={() => fixture.observeStop(!state.observedStop)}>
        {state.observedStop ? 'Simulate observed Clear' : 'Simulate observed Stop'}
      </button>
      <span className="fixture-journey__step" role="status">{state.label}</span>
      {visualCheck && <span role="status">{visualCheck}</span>}
    </aside>
    <div className="fixture-journey__app" ref={appViewportRef}><SuperbrainApp /></div>
  </div>;
}
