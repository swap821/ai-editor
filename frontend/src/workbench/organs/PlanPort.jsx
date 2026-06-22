import { useState, useCallback, useRef } from 'react';
import { API_BASE, API_HEADERS } from '../../config';
import { truncate } from './_fmt';

/* ─── PLAN PORT · CONFIDENCE-GATED DECOMPOSITION ───────────────────────────────
   A read-only probe into the planner: type a goal, see it decomposed into a
   confidence-gated step tree — each step tagged AUTO (its confidence cleared the
   gate) or ESCALATE (below threshold → human review), with the escalation reason.
   This NEVER executes: /plan decomposes only; running a step is a separate, gated
   action the planner has no power to trigger here.

   Data: a real POST /api/v1/plan { goal } via the product config base/headers.
   REQUEST-DRIVEN only — a plan fires on submit (Enter / button), never on a poll
   or bus event. The full ordered step list is rendered from plan.steps; the AUTO /
   ESCALATE verdict per step is DERIVED from plan.approved / plan.escalate (never
   re-formulated). Offline is per-request: a failed fetch keeps the input + prior
   tree and shows an inline offline note.
   ──────────────────────────────────────────────────────────────────────────── */

// verdict → row truth-state. approved=auto (ok); escalate=human review (busy).
const STEP_CLASS = { approved: 'ok', escalate: 'busy' };

function Step({ step }) {
  const cls = STEP_CLASS[step.verdict] ?? '';
  const auto = step.verdict === 'approved';
  return (
    <div className="organs-rung">
      <span className={`organs-dot organs-dot--${cls}`} aria-hidden="true" />
      <div className="organs-rung-main">
        <div className="organs-rung-top">
          <span className="organs-rung-lv">#{step.step_id}</span>
          <span className={`organs-rung-status organs-rung-status--${cls}`}>
            {auto ? 'AUTO' : 'ESCALATE'}
          </span>
        </div>
        <span className="organs-rung-prompt" title={step.description}>
          {step.description}
        </span>
        {!auto && step.reason && (
          <span className="organs-rung-prompt organs-rung-prompt--muted" title={step.reason}>
            {truncate(step.reason, 96)}
          </span>
        )}
      </div>
      <span className="organs-rung-stats">
        <span className={auto ? 'organs-stat-ok' : undefined}>
          {(step.confidence ?? 0).toFixed(2)}
        </span>
      </span>
    </div>
  );
}

export default function PlanPort() {
  const [goal, setGoal] = useState('');
  const [plan, setPlan] = useState(null); // null until first plan
  const [phase, setPhase] = useState('idle'); // idle|planning|result|empty|offline
  const [lastGoal, setLastGoal] = useState('');
  const inputRef = useRef(null);

  const runPlan = useCallback(async () => {
    const g = goal.trim();
    if (!g || phase === 'planning') return;
    setPhase('planning');
    setLastGoal(g);
    try {
      const r = await fetch(`${API_BASE}/api/v1/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...API_HEADERS },
        body: JSON.stringify({ goal: g }),
      });
      if (!r.ok) throw new Error(`bad status ${r.status}`);
      const json = await r.json();
      const steps = Array.isArray(json.steps) ? json.steps : [];
      if (steps.length === 0) {
        setPlan(null);
        setPhase('empty');
        return;
      }
      // Derive the per-step verdict from approved / escalate (never re-formulated).
      const approvedIds = new Set(
        (Array.isArray(json.approved) ? json.approved : []).map((s) => s.step_id)
      );
      const escalateById = new Map(
        (Array.isArray(json.escalate) ? json.escalate : []).map((e) => [e.step.step_id, e])
      );
      const tree = steps.map((s) => ({
        ...s,
        verdict: approvedIds.has(s.step_id) ? 'approved' : 'escalate',
        reason: escalateById.get(s.step_id)?.reason ?? '',
      }));
      setPlan({
        steps: tree,
        approvedCount: approvedIds.size,
        requiresHuman: Boolean(json.requires_human),
      });
      setPhase('result');
    } catch {
      // Keep the input + any prior tree; surface an inline offline note.
      setPhase('offline');
    }
  }, [goal, phase]);

  const onKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      runPlan();
    }
  };

  return (
    <section aria-label="Plan tree">
      <p className="organs-port-title">Reasoning · Plan Tree</p>

      <div className="organs-search">
        <input
          ref={inputRef}
          type="text"
          aria-label="Decompose a goal into a plan"
          placeholder="Decompose a goal…"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button
          type="button"
          onClick={runPlan}
          disabled={phase === 'planning' || !goal.trim()}
        >
          {phase === 'planning' ? '…' : 'Plan'}
        </button>
      </div>

      {phase === 'idle' && (
        <p className="organs-note">
          Decompose a goal into a confidence-gated step tree. Read-only — nothing
          runs.
        </p>
      )}

      {phase === 'planning' && (
        <>
          <div className="organs-skel" aria-hidden="true" />
          <div className="organs-skel" aria-hidden="true" />
        </>
      )}

      {phase === 'offline' && (
        <p className="organs-note organs-note--offline">
          PLAN OFFLINE — AI-OS unreachable.
        </p>
      )}

      {phase === 'empty' && (
        <p className="organs-note">
          Planner returned no usable steps for “{lastGoal}”.
        </p>
      )}

      {phase === 'result' && plan && (
        <>
          <div className="organs-strip">
            <span className="organs-strip-item">
              STEPS <b>{plan.steps.length}</b>
            </span>
            <span className="organs-strip-item">
              AUTO <b className="organs-stat-ok">{plan.approvedCount}</b>
            </span>
            <span className="organs-strip-item organs-strip-spacer">
              <span
                className={
                  plan.requiresHuman ? 'organs-rung-status--busy' : 'organs-rung-status--ok'
                }
              >
                {plan.requiresHuman ? 'HUMAN REVIEW' : 'ALL CLEAR'}
              </span>
            </span>
          </div>
          <div>
            {plan.steps.map((s) => (
              <Step key={s.step_id} step={s} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
