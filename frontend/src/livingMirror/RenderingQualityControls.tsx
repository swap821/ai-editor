import { useId } from 'react';
import { isQualityPreference } from '../superbrain/lib/renderQualityPolicy';
import { useQualityTierOwner } from '../superbrain/components/qualityTierContext';

/** One explicit preference; measured Auto stages are session-only, never saved. */
export function RenderingQualityControls() {
  const owner = useQualityTierOwner();
  const id = useId();
  if (!owner) return null;

  return (
    <span className="lm-rendering-preferences" role="group" aria-label="Rendering preferences" aria-live="off">
      <label htmlFor={id}>Visual detail</label>
      <select
        id={id}
        value={owner.preference}
        aria-describedby={`${id}-help`}
        onChange={(event) => {
          const tier = event.currentTarget.value;
          if (isQualityPreference(tier)) owner.setTier(tier);
        }}
      >
        <option value="auto">Auto</option>
        <option value="high">High detail</option>
        <option value="medium">Balanced</option>
        <option value="low">Economy</option>
      </select>
      <span id={`${id}-help`} className="lm-rendering-preferences__help">{owner.preference === 'auto'
        ? 'Optional detail adapts to frame pacing. Work and controls stay intact.'
        : 'Manual detail; resolution adapts within its limits.'}</span>
    </span>
  );
}
