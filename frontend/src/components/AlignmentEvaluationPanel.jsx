import { useEffect, useState } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import { fetchAlignmentEvaluation } from '../lib/alignmentEvaluation';

function percent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function words(value) {
  return String(value || 'unknown').replaceAll('_', ' ');
}

function Metric({ label, value, detail }) {
  return (
    <div style={{
      minWidth: 125, padding: '10px 12px', borderRadius: 9,
      background: 'var(--surface-1)', border: '1px solid var(--border)',
    }}>
      <div style={{ color: 'var(--text-3)', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {label}
      </div>
      <div style={{ color: 'var(--text-1)', fontSize: 19, fontWeight: 750, marginTop: 3 }}>
        {value}
      </div>
      {detail && <div style={{ color: 'var(--text-3)', fontSize: 9, marginTop: 2 }}>{detail}</div>}
    </div>
  );
}

function Counts({ title, values }) {
  const entries = Object.entries(values || {}).sort((a, b) => b[1] - a[1]);
  return (
    <div style={{
      flex: 1, minWidth: 180, padding: '10px 12px', borderRadius: 9,
      background: 'var(--surface-1)', border: '1px solid var(--border)',
    }}>
      <div style={{ color: 'var(--text-3)', fontSize: 9, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
        {title}
      </div>
      {entries.length === 0 ? (
        <div style={{ color: 'var(--text-3)', fontSize: 10 }}>No evidence yet.</div>
      ) : entries.map(([name, count]) => (
        <div key={name} style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-2)', fontSize: 10, lineHeight: 1.7 }}>
          <span>{words(name)}</span><strong>{count}</strong>
        </div>
      ))}
    </div>
  );
}

export default function AlignmentEvaluationPanel({ refreshKey = 0 }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setSummary(await fetchAlignmentEvaluation());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    fetchAlignmentEvaluation()
      .then(data => {
        if (!cancelled) {
          setSummary(data);
          setError('');
        }
      })
      .catch(err => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [refreshKey]);

  return (
    <section aria-label="Alignment evaluation" style={{ height: '100%', overflowY: 'auto', padding: 14, color: 'var(--text-2)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 12 }}>
        <Activity size={14} style={{ color: 'var(--accent)' }} />
        <strong style={{ color: 'var(--text-1)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Human Alignment Evaluation
        </strong>
        <button type="button" onClick={load} disabled={loading} style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5 }}>
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      <div style={{ color: 'var(--text-3)', fontSize: 9.5, marginBottom: 10 }}>
        Diagnostic human evidence only. It never approves actions or automatically changes policy.
      </div>

      {error && <div role="alert" style={{ color: 'var(--danger)', fontSize: 10 }}>{error}</div>}
      {loading && !summary && <div style={{ color: 'var(--text-3)', fontSize: 10 }}>Loading evaluation evidence...</div>}
      {summary && (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 9 }}>
            <Metric label="Observed turns" value={summary.total_turns} />
            <Metric label="Correction rate" value={percent(summary.correction_rate)} detail={`${summary.corrected_turns} corrected`} />
            <Metric label="Human labels" value={summary.human_feedback_count} detail={`${percent(summary.positive_feedback_rate)} positive`} />
            <Metric label="Asked first" value={percent(summary.ask_rate)} />
            <Metric label="Stated assumptions" value={percent(summary.state_assumptions_rate)} />
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 9 }}>
            <Counts title="Human outcomes" values={summary.outcomes} />
            <Counts title="Reported issues" values={summary.issues} />
            <Counts title="Corrected fields" values={summary.corrected_fields} />
            <Counts title="Ambiguity actions" values={summary.by_ambiguity_action} />
          </div>
          <div style={{
            padding: '10px 12px', borderRadius: 9, background: 'var(--surface-1)',
            border: '1px solid var(--border)',
          }}>
            <div style={{ color: 'var(--text-3)', fontSize: 9, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
              Repeated review candidates (3+ observations)
            </div>
            {(summary.repeated_patterns || []).length === 0 ? (
              <div style={{ color: 'var(--text-3)', fontSize: 10 }}>No repeated pattern has enough evidence yet.</div>
            ) : summary.repeated_patterns.map(item => (
              <div key={`${item.kind}-${item.name}`} style={{ color: 'var(--text-2)', fontSize: 10, lineHeight: 1.7 }}>
                {words(item.kind)}: {words(item.name)} ({item.count})
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
