import { useState, useEffect, useCallback, useRef } from 'react';
import { API_BASE, API_HEADERS } from '../../config';
import { truncate } from './_fmt';

/* ─── MODELS PORT · BRAIN READINESS ────────────────────────────────────────────
   A read-only readout of which brains the agent can actually route to right now:
   the local Ollama chat models, the cloud providers (Bedrock / Gemini) and their
   configured-vs-available state, and the agent's AUTO routing table (which model
   it picks per task). Pure discovery — nothing is invoked.

   Data: four real parallel GETs (/models/local, /bedrock, /gemini, /auto) via the
   product config base/headers. Promise.allSettled so one provider being down never
   blanks the others. FETCH-ON-OPEN only — provider readiness is static-ish, so no
   bus subscription and no poll. Honest offline: a prior good fetch keeps the last
   data with a `· stale` tag; an all-down first fetch shows the offline note.
   ──────────────────────────────────────────────────────────────────────────── */

const TASK_LABEL = ['coding', 'reasoning', 'general', 'fast'];

// Local: ready iff it lists tool-capable chat models.
function localReadiness(local) {
  const models = Array.isArray(local?.models) ? local.models : [];
  if (models.length > 0) {
    return { cls: 'ok', word: 'READY', count: models.length, detail: models.join(' · ') };
  }
  return { cls: '', word: local ? 'NONE' : 'OFFLINE', count: 0, detail: '' };
}

// Cloud (Bedrock / Gemini): READY when available; CONFIGURED but not reachable; OFF.
function cloudReadiness(p) {
  const models = Array.isArray(p?.models) ? p.models : [];
  const detail = models.map((m) => m.name || m.id).filter(Boolean).join(' · ');
  if (p?.available) return { cls: 'ok', word: 'READY', detail };
  if (p?.configured) return { cls: 'busy', word: 'CONFIGURED', detail };
  return { cls: '', word: 'OFF', detail: '' };
}

function ProviderRow({ name, readiness }) {
  const { cls, word, detail, count } = readiness;
  return (
    <div className={`organs-row organs-row--${cls}`} data-ready={word}>
      <span className={`organs-dot organs-dot--${cls}`} aria-hidden="true" />
      <div className="organs-row-main">
        <div className="organs-row-label">
          <span className="organs-row-name">{name}</span>
        </div>
        {detail && (
          <span className="organs-row-eyebrow" title={detail}>
            {truncate(detail, 80)}
          </span>
        )}
      </div>
      <div className="organs-row-stats">
        <span className={`organs-rung-status${cls ? ` organs-rung-status--${cls}` : ''}`}>
          {word}
        </span>
        {count > 0 && <span>{count}</span>}
      </div>
    </div>
  );
}

export default function ModelsPort() {
  const [data, setData] = useState(null); // null = not yet loaded
  const [phase, setPhase] = useState('loading'); // loading|live|stale|offline
  const hadDataRef = useRef(false);

  const fetchModels = useCallback(async () => {
    try {
      const [local, bedrock, gemini, auto] = await Promise.allSettled([
        fetch(`${API_BASE}/api/v1/models/local`, { headers: API_HEADERS }),
        fetch(`${API_BASE}/api/v1/models/bedrock`, { headers: API_HEADERS }),
        fetch(`${API_BASE}/api/v1/models/gemini`, { headers: API_HEADERS }),
        fetch(`${API_BASE}/api/v1/models/auto`, { headers: API_HEADERS }),
      ]);
      const j = async (s) =>
        s.status === 'fulfilled' && s.value.ok ? s.value.json() : null;
      const next = {
        local: await j(local),
        bedrock: await j(bedrock),
        gemini: await j(gemini),
        auto: await j(auto),
      };
      if (!next.local && !next.bedrock && !next.gemini && !next.auto) {
        throw new Error('all down');
      }
      hadDataRef.current = true;
      setData(next);
      setPhase('live');
    } catch {
      setPhase(hadDataRef.current ? 'stale' : 'offline');
    }
  }, []);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  if (phase === 'loading' && data === null) {
    return (
      <section aria-label="Model readiness">
        <p className="organs-port-title">System · Brains Ready</p>
        <div className="organs-skel" aria-hidden="true" />
        <div className="organs-skel" aria-hidden="true" />
      </section>
    );
  }

  if (phase === 'offline' && data === null) {
    return (
      <section aria-label="Model readiness">
        <p className="organs-port-title">System · Brains Ready</p>
        <p className="organs-note organs-note--offline">
          MODELS OFFLINE — AI-OS unreachable.
        </p>
      </section>
    );
  }

  const local = localReadiness(data?.local);
  const bedrock = cloudReadiness(data?.bedrock);
  const gemini = cloudReadiness(data?.gemini);
  const auto = data?.auto;
  const byTask = auto?.by_task ?? {};
  const noneReady = local.cls !== 'ok' && bedrock.cls !== 'ok' && gemini.cls !== 'ok';

  return (
    <section aria-label="Model readiness">
      <p className="organs-port-title">
        System · Brains Ready
        {phase === 'stale' && <span className="organs-stale">· stale</span>}
      </p>

      <ProviderRow name="Local" readiness={local} />
      <ProviderRow name="Bedrock" readiness={bedrock} />
      <ProviderRow name="Gemini" readiness={gemini} />

      {noneReady && (
        <p className="organs-note">
          No brains ready. Install a local model or configure a cloud provider.
        </p>
      )}

      {auto && (
        <div className="organs-skill" data-open="true">
          <div className="organs-skill-head" aria-hidden="true">
            <span className="organs-skill-name">AUTO ROUTING</span>
            <span className="organs-skill-summary">{auto.available ? 'LIVE' : 'NONE'}</span>
          </div>
          <div className="organs-rungs">
            {TASK_LABEL.map((task) => {
              const model = byTask[task];
              const isChosen = auto.available && auto.model && model === auto.model;
              return (
                <div className="organs-rung" key={task}>
                  <span
                    className={`organs-dot organs-dot--${isChosen ? 'ok' : ''}`}
                    aria-hidden="true"
                  />
                  <div className="organs-rung-main">
                    <div className="organs-rung-top">
                      <span className="organs-rung-lv">{task.toUpperCase()}</span>
                    </div>
                    <span
                      className={`organs-rung-prompt${isChosen ? ' organs-stat-ok' : ''}`}
                      title={model || 'no local chat model'}
                    >
                      {model || '—'}
                    </span>
                    {isChosen && auto.reason && (
                      <span
                        className="organs-rung-prompt organs-rung-prompt--muted"
                        title={auto.reason}
                      >
                        {truncate(auto.reason, 80)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
