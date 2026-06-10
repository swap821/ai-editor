import { useState } from 'react';

const LABELS = {
  constraints: 'Constraints',
  assumptions: 'Assumptions',
  unknowns: 'Unknowns',
  decisions: 'Decisions',
};

function words(value) {
  return String(value || 'unknown').replaceAll('_', ' ');
}

function lines(value) {
  return Array.isArray(value) ? value.join('\n') : '';
}

function draftFrom(frame) {
  return {
    goal: frame.goal || '',
    intent: frame.intent || 'unknown',
    desired_outcome: frame.desired_outcome || '',
    next_action: frame.next_action || '',
    communication_mode: frame.communication?.mode || 'direct',
    constraints: lines(frame.constraints),
    assumptions: lines(frame.assumptions),
    unknowns: lines(frame.unknowns),
    decisions: lines(frame.decisions),
  };
}

function correctionDiff(frame, draft) {
  const corrections = {};
  for (const key of ['goal', 'intent', 'desired_outcome', 'next_action']) {
    if ((frame[key] || '') !== draft[key].trim()) corrections[key] = draft[key].trim();
  }
  if ((frame.communication?.mode || 'direct') !== draft.communication_mode) {
    corrections.communication_mode = draft.communication_mode;
  }
  for (const key of ['constraints', 'assumptions', 'unknowns', 'decisions']) {
    const value = draft[key].split('\n').map(item => item.trim()).filter(Boolean);
    if (JSON.stringify(frame[key] || []) !== JSON.stringify(value)) corrections[key] = value;
  }
  return corrections;
}

function DetailList({ label, items }) {
  if (!Array.isArray(items) || items.length === 0) return null;
  return (
    <div>
      <div style={{
        color: 'var(--text-3)', fontSize: 9, fontWeight: 800,
        letterSpacing: '0.09em', textTransform: 'uppercase', marginBottom: 3,
      }}>
        {label}
      </div>
      <ul style={{
        margin: '0 0 7px 15px', padding: 0, color: 'var(--text-2)',
        fontSize: 10.5, lineHeight: 1.45,
      }}>
        {items.map((item, index) => <li key={`${label}-${index}`}>{item}</li>)}
      </ul>
    </div>
  );
}

export default function AlignmentPanel({
  frame,
  correctionHistory = [],
  onCorrect,
  onClearCorrection,
  onFeedback,
}) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({});
  const [error, setError] = useState('');
  const [feedbackStatus, setFeedbackStatus] = useState('');
  if (!frame) return null;

  const confidence = Number.isFinite(Number(frame.confidence))
    ? `${Math.round(Number(frame.confidence) * 100)}%`
    : 'unknown';
  const communication = frame.communication || {};
  const correction = frame.correction || {};

  const startEditing = () => {
    setDraft(draftFrom(frame));
    setError('');
    setEditing(true);
  };

  const submitCorrection = async (event) => {
    event.preventDefault();
    const corrections = correctionDiff(frame, draft);
    if (Object.keys(corrections).length === 0) {
      setError('Change at least one field before saving.');
      return;
    }
    try {
      await onCorrect?.(corrections);
      setEditing(false);
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  const clearCorrection = async () => {
    try {
      await onClearCorrection?.();
      setEditing(false);
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  const submitFeedback = async (outcome, issues = []) => {
    setFeedbackStatus('');
    try {
      await onFeedback?.({ outcome, issues });
      setFeedbackStatus('Feedback recorded for this understanding frame.');
    } catch (err) {
      setFeedbackStatus(`Feedback error: ${err.message}`);
    }
  };

  return (
    <section
      aria-label="Shared understanding"
      style={{
        flexShrink: 0,
        margin: '9px 10px 0',
        borderRadius: 11,
        background: 'linear-gradient(180deg, rgba(59,130,246,0.10), rgba(18,19,26,0.72))',
        border: '1px solid rgba(96,165,250,0.24)',
        boxShadow: 'var(--elevation-1)',
        overflow: 'hidden',
      }}
    >
      <div style={{ padding: '9px 10px 8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
          <span style={{
            color: 'var(--accent-400)', fontSize: 9.5, fontWeight: 800,
            letterSpacing: '0.09em', textTransform: 'uppercase',
          }}>
            Shared understanding
          </span>
          <span style={{
            color: 'var(--text-3)', fontSize: 9, border: '1px solid var(--border-strong)',
            borderRadius: 999, padding: '1px 5px', textTransform: 'capitalize',
          }}>
            {frame.intent || 'unknown'}
          </span>
          <span style={{
            color: 'var(--text-3)', fontSize: 9, border: '1px solid var(--border-strong)',
            borderRadius: 999, padding: '1px 5px', textTransform: 'capitalize',
          }}>
            {words(communication.mode)} mode
          </span>
          {correction.active && (
            <span style={{
              color: '#fbbf24', fontSize: 9, border: '1px solid rgba(251,191,36,0.35)',
              borderRadius: 999, padding: '1px 5px',
            }}>
              user corrected
            </span>
          )}
          <span style={{ marginLeft: 'auto', color: 'var(--text-3)', fontSize: 9 }}>
            {confidence} interpretation
          </span>
        </div>

        <div style={{
          color: 'var(--text-1)', fontSize: 11.5, fontWeight: 650,
          lineHeight: 1.4, marginBottom: 4,
        }}>
          {frame.goal}
        </div>
        <div style={{ color: 'var(--text-2)', fontSize: 10.5, lineHeight: 1.4 }}>
          Next: {frame.next_action}
        </div>
        <div style={{ color: 'var(--text-3)', fontSize: 9.5, lineHeight: 1.4, marginTop: 3 }}>
          Ambiguity policy: {words(communication.ambiguity_action)}
        </div>

        <button
          type="button"
          onClick={() => setExpanded(value => !value)}
          aria-expanded={expanded}
          style={{
            marginTop: 7, padding: 0, border: 0, background: 'transparent',
            color: 'var(--accent-400)', fontFamily: 'inherit', fontSize: 9.5,
            fontWeight: 700, cursor: 'pointer',
          }}
        >
          {expanded ? 'Hide details' : 'Inspect details'}
        </button>
        {onCorrect && (
          <button
            type="button"
            onClick={startEditing}
            style={{
              margin: '7px 0 0 10px', padding: 0, border: 0, background: 'transparent',
              color: 'var(--accent-400)', fontFamily: 'inherit', fontSize: 9.5,
              fontWeight: 700, cursor: 'pointer',
            }}
          >
            Correct understanding
          </button>
        )}
      </div>

      {editing && (
        <form
          onSubmit={submitCorrection}
          style={{
            padding: '9px 10px', borderTop: '1px solid rgba(96,165,250,0.16)',
            background: 'rgba(5,5,7,0.32)',
          }}
        >
          {[
            ['goal', 'Goal'],
            ['desired_outcome', 'Desired outcome'],
            ['next_action', 'Next action'],
          ].map(([key, label]) => (
            <label key={key} style={{ display: 'block', marginBottom: 6, color: 'var(--text-3)', fontSize: 9 }}>
              {label}
              <input
                aria-label={label}
                value={draft[key] || ''}
                onChange={event => setDraft(value => ({ ...value, [key]: event.target.value }))}
                style={{
                  width: '100%', boxSizing: 'border-box', marginTop: 2, padding: '5px 6px',
                  borderRadius: 5, border: '1px solid var(--border)', background: 'var(--surface-2)',
                  color: 'var(--text-1)', fontFamily: 'inherit', fontSize: 10,
                }}
              />
            </label>
          ))}
          <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
            {[['intent', 'Intent', ['discuss', 'teach', 'plan', 'execute', 'review', 'decide', 'correct', 'unknown']],
              ['communication_mode', 'Communication mode', ['direct', 'collaborative', 'explanatory']]].map(([key, label, options]) => (
              <label key={key} style={{ flex: 1, color: 'var(--text-3)', fontSize: 9 }}>
                {label}
                <select
                  aria-label={label}
                  value={draft[key] || options[0]}
                  onChange={event => setDraft(value => ({ ...value, [key]: event.target.value }))}
                  style={{
                    width: '100%', marginTop: 2, padding: '4px', borderRadius: 5,
                    border: '1px solid var(--border)', background: 'var(--surface-2)',
                    color: 'var(--text-1)', fontFamily: 'inherit', fontSize: 10,
                  }}
                >
                  {options.map(option => <option key={option}>{option}</option>)}
                </select>
              </label>
            ))}
          </div>
          {['constraints', 'assumptions', 'unknowns', 'decisions'].map(key => (
            <label key={key} style={{ display: 'block', marginBottom: 6, color: 'var(--text-3)', fontSize: 9 }}>
              {words(key)} (one per line)
              <textarea
                aria-label={words(key)}
                rows={2}
                value={draft[key] || ''}
                onChange={event => setDraft(value => ({ ...value, [key]: event.target.value }))}
                style={{
                  width: '100%', boxSizing: 'border-box', marginTop: 2, padding: '5px 6px',
                  borderRadius: 5, border: '1px solid var(--border)', background: 'var(--surface-2)',
                  color: 'var(--text-1)', fontFamily: 'inherit', fontSize: 10, resize: 'vertical',
                }}
              />
            </label>
          ))}
          {error && <div role="alert" style={{ color: '#fca5a5', fontSize: 9.5, marginBottom: 6 }}>{error}</div>}
          <div style={{ display: 'flex', gap: 6 }}>
            <button type="submit">Save correction</button>
            <button type="button" onClick={() => setEditing(false)}>Cancel</button>
            {correction.active && onClearCorrection && (
              <button type="button" onClick={clearCorrection}>Clear active correction</button>
            )}
          </div>
          <div style={{ color: 'var(--text-3)', fontSize: 9, lineHeight: 1.4, marginTop: 6 }}>
            Corrections override interpretation only. They never approve actions or become evidence.
          </div>
        </form>
      )}

      {expanded && (
        <div style={{
          padding: '8px 10px 9px', borderTop: '1px solid rgba(96,165,250,0.16)',
          background: 'rgba(5,5,7,0.20)',
        }}>
          {frame.desired_outcome && (
            <div style={{ marginBottom: 7 }}>
              <div style={{
                color: 'var(--text-3)', fontSize: 9, fontWeight: 800,
                letterSpacing: '0.09em', textTransform: 'uppercase', marginBottom: 3,
              }}>
                Desired outcome
              </div>
              <div style={{ color: 'var(--text-2)', fontSize: 10.5, lineHeight: 1.45 }}>
                {frame.desired_outcome}
              </div>
            </div>
          )}
          {Object.entries(LABELS).map(([key, label]) => (
            <DetailList key={key} label={label} items={frame[key]} />
          ))}
          <DetailList
            label="Policy reasons"
            items={Array.isArray(communication.reasons) ? communication.reasons.map(words) : []}
          />
          {communication.clarifying_question && (
            <div style={{ color: 'var(--text-2)', fontSize: 10.5, lineHeight: 1.45, marginBottom: 7 }}>
              Clarifying question: {communication.clarifying_question}
            </div>
          )}
          {correctionHistory.length > 0 && (
            <div style={{ marginBottom: 7 }}>
              <div style={{
                color: 'var(--text-3)', fontSize: 9, fontWeight: 800,
                letterSpacing: '0.09em', textTransform: 'uppercase', marginBottom: 3,
              }}>
                Correction history
              </div>
              {correctionHistory.slice(0, 5).map(item => (
                <div key={item.revision} style={{ color: 'var(--text-2)', fontSize: 9.5, lineHeight: 1.4 }}>
                  Revision {item.revision}: {words(item.status)} · {(item.corrected_fields || []).map(words).join(', ')}
                </div>
              ))}
            </div>
          )}
          {onFeedback && (
            <div style={{ marginBottom: 8 }}>
              <div style={{
                color: 'var(--text-3)', fontSize: 9, fontWeight: 800,
                letterSpacing: '0.09em', textTransform: 'uppercase', marginBottom: 4,
              }}>
                Human evaluation
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                <button type="button" onClick={() => submitFeedback('aligned')}>Mark aligned</button>
                <button type="button" onClick={() => submitFeedback('misaligned', ['wrong_goal'])}>Wrong goal</button>
                <button type="button" onClick={() => submitFeedback('misaligned', ['wrong_intent'])}>Wrong intent</button>
                <button type="button" onClick={() => submitFeedback('misaligned', ['unnecessary_question'])}>Unnecessary question</button>
                <button type="button" onClick={() => submitFeedback('misaligned', ['risky_assumption'])}>Risky assumption</button>
                <button type="button" onClick={() => submitFeedback('misaligned', ['wrong_mode'])}>Wrong mode</button>
                {correction.active && (
                  <>
                    <button type="button" onClick={() => submitFeedback('correction_helped')}>Correction helped</button>
                    <button type="button" onClick={() => submitFeedback('correction_not_helpful')}>Correction not helpful</button>
                  </>
                )}
              </div>
              {feedbackStatus && (
                <div role="status" style={{ color: 'var(--text-3)', fontSize: 9, marginTop: 4 }}>
                  {feedbackStatus}
                </div>
              )}
            </div>
          )}
          <div style={{ color: 'var(--text-3)', fontSize: 9, lineHeight: 1.4 }}>
            Advisory interpretation and communication policy only. They are not approval or
            verified evidence.
          </div>
        </div>
      )}
    </section>
  );
}
