'use client';

/**
 * SwarmHUD — a minimal, read-only status overlay for an ant-colony swarm turn.
 *
 * Shows the decomposed plan as numbered pills and the currently active caste,
 * so the operator can see the swarm working without parsing tool chatter.
 */

import { useEffect, useState } from 'react';
import { getSwarmHUDState, subscribeSwarmHUD, type SwarmHUDState } from '@/lib/swarmHUDStore';

function useSwarmHUD(): SwarmHUDState {
  const [state, setState] = useState<SwarmHUDState>(getSwarmHUDState);
  useEffect(() => subscribeSwarmHUD(setState), []);
  return state;
}

export default function SwarmHUD() {
  const { active, plan, activeCastes, completedLegs, cloudIndices } = useSwarmHUD();
  if (!active || plan.length === 0) return null;

  return (
    <div className="swarm-hud" role="status" aria-label="Swarm progress">
      <div className="swarm-hud__header">
        <span className="swarm-hud__title">SWARM</span>
        <span className="swarm-hud__counts">
          {plan.length} subtask{plan.length === 1 ? '' : 's'}
          {cloudIndices.length > 0 ? ` · ${cloudIndices.length} cloud` : ''}
          {completedLegs > 0 ? ` · ${completedLegs} done` : ''}
        </span>
      </div>

      <ol className="swarm-hud__plan">
        {plan.map((subtask, index) => {
          const isCloud = cloudIndices.includes(index);
          const isActive = activeCastes.some((c) => c.startsWith(`worker-${index + 1}`));
          const isDone = completedLegs > index && !isActive;
          return (
            <li
              key={index}
              className={`swarm-hud__pill${isActive ? ' is-active' : ''}${isDone ? ' is-done' : ''}${isCloud ? ' is-cloud' : ''}`}
              title={subtask}
            >
              <span className="swarm-hud__index">{index + 1}</span>
              <span className="swarm-hud__label">{subtask}</span>
              {isCloud ? <span className="swarm-hud__cloud" aria-label="cloud" /> : null}
            </li>
          );
        })}
      </ol>

      {activeCastes.length > 0 ? (
        <div className="swarm-hud__caste" aria-live="polite">
          {activeCastes.map((c) => c.toUpperCase()).join(' · ')}
        </div>
      ) : null}
    </div>
  );
}
