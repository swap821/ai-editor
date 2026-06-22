import { useState, useEffect, useCallback, useRef } from 'react';
import { API_BASE, API_HEADERS } from '../../config';
import { subscribeCognition } from '../../superbrain/lib/cognitionBus';

/* ─── CURRICULUM PORT ──────────────────────────────────────────────────────────
   The brain-growth ladder: every skill's levels, the evidence (successes/attempts)
   behind each rung, and the held-out flag that proves the brain GENERALIZED rather
   than memorized. Read-only.

   Data: a real GET to /api/v1/development/curriculum via the product's config base
   (API_BASE/API_HEADERS — the same base ForgePorts uses for /development/workspace).
   Mastery is DERIVED, never re-formulated: a level is mastered iff the backend set
   the row status to 'mastered' (the backend's _refresh_level already computed it).
   No invented pass-rate gate.

   Refresh: on open + bounded burst on SKILL MASTERED / knowledge-acquired bus
   events. Poll-only otherwise (no continuous timer). Honest offline: keep last good
   data with a `· stale` tag, never fabricate.
   ──────────────────────────────────────────────────────────────────────────── */

const truncate = (s, n) => {
  const str = String(s || '');
  return str.length > n ? `${str.slice(0, n - 1)}…` : str;
};

const STATUS_CLASS = { mastered: 'ok', available: 'busy', locked: '' };

function Rung({ task }) {
  const status = task.status;
  const cls = STATUS_CLASS[status] ?? '';
  const heldOut = task.held_out === 1 || task.held_out === true;
  const proven = heldOut && (task.successes ?? 0) > 0;
  return (
    <div className="organs-rung">
      <span className={`organs-dot organs-dot--${cls}`} aria-hidden="true" />
      <div className="organs-rung-main">
        <div className="organs-rung-top">
          <span className="organs-rung-lv">LV {task.level}</span>
          <span className={`organs-rung-status${cls ? ` organs-rung-status--${cls}` : ''}`}>
            {status}
          </span>
          {heldOut && (
            <span
              className={`organs-held${proven ? ' organs-held--proven' : ''}`}
              title={
                proven
                  ? 'Held-out task passed — generalization proven'
                  : 'Held-out task — generalization pending'
              }
            >
              {proven ? 'HELD-OUT ✓' : 'HELD-OUT'}
            </span>
          )}
        </div>
        {task.prompt && (
          <span className="organs-rung-prompt" title={task.prompt}>
            {truncate(task.prompt, 64)}
          </span>
        )}
      </div>
      <span className="organs-rung-stats">
        {(task.attempts ?? 0) > 0 ? (
          <>
            <span className={task.successes > 0 ? 'organs-stat-ok' : undefined}>✓{task.successes ?? 0}</span>
            /{task.attempts}
          </>
        ) : (
          '—'
        )}
      </span>
    </div>
  );
}

function SkillGroup({ name, tasks }) {
  const [open, setOpen] = useState(true);
  const levels = [...tasks].sort((a, b) => (a.level ?? 0) - (b.level ?? 0));
  const maxLevel = levels.reduce((m, t) => Math.max(m, t.level ?? 0), 0);
  const maxMastered = levels.reduce(
    (m, t) => (t.status === 'mastered' ? Math.max(m, t.level ?? 0) : m),
    0
  );
  return (
    <div className="organs-skill" data-open={open}>
      <button
        type="button"
        className="organs-skill-head"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="organs-chevron" aria-hidden="true">▶</span>
        <span className="organs-skill-name">{name}</span>
        <span className="organs-skill-summary">
          L{maxMastered}/{maxLevel} mastered
        </span>
      </button>
      {open && (
        <div className="organs-rungs">
          {levels.map((t) => (
            <Rung key={t.id} task={t} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function CurriculumPort() {
  const [tasks, setTasks] = useState(null); // null = not yet loaded
  const [phase, setPhase] = useState('loading'); // loading|live|stale|offline
  const timersRef = useRef([]);
  // Whether a prior fetch ever succeeded — decides STALE (keep last good) vs
  // OFFLINE on a later failure.
  const hadDataRef = useRef(false);

  const fetchCurriculum = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/v1/development/curriculum`, {
        headers: API_HEADERS,
      });
      if (!r.ok) throw new Error(`bad status ${r.status}`);
      const json = await r.json();
      hadDataRef.current = true;
      setTasks(Array.isArray(json.tasks) ? json.tasks : []);
      setPhase('live');
    } catch {
      setPhase(hadDataRef.current ? 'stale' : 'offline');
    }
  }, []);

  useEffect(() => {
    fetchCurriculum();
    const unsub = subscribeCognition((e) => {
      if (!e || e.type === 'telemetry') return;
      const label = String(e.label || '');
      if (
        e.type === 'knowledge-acquired' ||
        /^SKILL MASTERED/.test(label)
      ) {
        timersRef.current.forEach(clearTimeout);
        timersRef.current = [350, 1500, 3500].map((d) =>
          setTimeout(fetchCurriculum, d)
        );
      }
    });
    return () => {
      unsub();
      timersRef.current.forEach(clearTimeout);
    };
  }, [fetchCurriculum]);

  if (phase === 'loading' && tasks === null) {
    return (
      <section aria-label="Curriculum growth ladder">
        <p className="organs-port-title">Curriculum · Growth Ladder</p>
        <div className="organs-skel" aria-hidden="true" />
        <div className="organs-skel" aria-hidden="true" />
      </section>
    );
  }

  if (phase === 'offline' && tasks === null) {
    return (
      <section aria-label="Curriculum growth ladder">
        <p className="organs-port-title">Curriculum · Growth Ladder</p>
        <p className="organs-note organs-note--offline">
          CURRICULUM OFFLINE — AI-OS unreachable.
        </p>
      </section>
    );
  }

  const list = Array.isArray(tasks) ? tasks : [];

  // Group by skill_name, preserving first-seen order (endpoint already orders by
  // skill_name, level, held_out, id).
  const groups = [];
  const index = new Map();
  for (const t of list) {
    const key = t.skill_name || '(unnamed)';
    if (!index.has(key)) {
      index.set(key, groups.length);
      groups.push({ name: key, tasks: [] });
    }
    groups[index.get(key)].tasks.push(t);
  }

  return (
    <section aria-label="Curriculum growth ladder">
      <p className="organs-port-title">
        Curriculum · Growth Ladder
        {phase === 'stale' && <span className="organs-stale">· stale</span>}
      </p>
      {groups.length === 0 ? (
        <p className="organs-note">
          No curriculum defined yet. Levels unlock as the brain masters the one
          below.
        </p>
      ) : (
        groups.map((g) => (
          <SkillGroup key={g.name} name={g.name} tasks={g.tasks} />
        ))
      )}
    </section>
  );
}
