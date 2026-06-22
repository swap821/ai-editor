import { useState, useCallback, useRef } from 'react';
import { API_BASE, API_HEADERS } from '../../config';
import { truncate } from './_fmt';

/* ─── MEMORY SEARCH PORT · L3 SEMANTIC PROBE ───────────────────────────────────
   A read-only probe into the brain's L3 semantic memory: type a query, see the
   hybrid BM25 + FAISS-vector + temporal-recency retrieval scored and ranked, with
   the component sub-scores exposed (the whole point of surfacing L3 — explainable
   recall, not a black box).

   Data: a real POST /api/v1/memory/search { query, top_k:8 } via the product
   config base/headers. This port is REQUEST-DRIVEN only — a search fires on submit
   (Enter / button), never on a poll or bus event. No ambient seed (search has no
   resting state). Offline is per-request: a failed fetch keeps the input + any
   prior results and shows an inline offline note so retry is one Enter away.
   ──────────────────────────────────────────────────────────────────────────── */

const TOP_K = 8;

// verification_status → row truth-state. verified=ok; a recognized failure status
// is a fault (red); everything else (unverified) is neutral.
function verifyClass(status) {
  if (status === 'verified') return 'ok';
  if (status === 'unverified' || !status) return '';
  return 'bad'; // refuted / failed / any explicit non-verified-non-unverified state
}
function verifyLabel(status) {
  if (status === 'verified') return 'VERIFIED';
  if (status === 'unverified' || !status) return 'unverified';
  return String(status);
}

function Row({ hit }) {
  const cls = verifyClass(hit.verification_status);
  return (
    <div className={`organs-row organs-row--${cls}`} data-verify={hit.verification_status}>
      <span className={`organs-dot organs-dot--${cls}`} aria-hidden="true" />
      <div className="organs-row-main">
        <div className="organs-row-label">
          <span className="organs-row-name" title={hit.text}>
            {truncate(hit.text, 140)}
          </span>
        </div>
        <span className="organs-row-eyebrow">
          {hit.memory_type} · #{hit.id} ·{' '}
          <span className={cls === 'ok' ? 'organs-stat-ok' : undefined}>
            {verifyLabel(hit.verification_status)}
          </span>
        </span>
      </div>
      <div className="organs-row-stats">
        <span className="organs-score">{(hit.score ?? 0).toFixed(3)}</span>
        <span className="organs-stat-streak" title="BM25 · FAISS-vector · recency sub-scores.">
          b{(hit.bm25 ?? 0).toFixed(2)} f{(hit.faiss ?? 0).toFixed(2)} r
          {(hit.recency ?? 0).toFixed(2)}
        </span>
      </div>
    </div>
  );
}

export default function MemorySearchPort() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null); // null until first search
  const [phase, setPhase] = useState('idle'); // idle|searching|results|empty|offline
  const [lastQuery, setLastQuery] = useState('');
  const inputRef = useRef(null);

  const runSearch = useCallback(async () => {
    const q = query.trim();
    if (!q || phase === 'searching') return;
    setPhase('searching');
    setLastQuery(q);
    try {
      const r = await fetch(`${API_BASE}/api/v1/memory/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...API_HEADERS },
        body: JSON.stringify({ query: q, top_k: TOP_K }),
      });
      if (!r.ok) throw new Error(`bad status ${r.status}`);
      const json = await r.json();
      const hits = Array.isArray(json.results) ? json.results : [];
      setResults(hits);
      setPhase(hits.length ? 'results' : 'empty');
    } catch {
      // Keep the input + any prior results; surface an inline offline note.
      setPhase('offline');
    }
  }, [query, phase]);

  const onKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      runSearch();
    }
  };

  return (
    <section aria-label="Semantic memory search">
      <p className="organs-port-title">Memory · L3 Semantic Probe</p>

      <div className="organs-search">
        <input
          ref={inputRef}
          type="text"
          aria-label="Search semantic memory"
          placeholder="Search the brain's memory…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button
          type="button"
          onClick={runSearch}
          disabled={phase === 'searching' || !query.trim()}
        >
          {phase === 'searching' ? '…' : 'Search'}
        </button>
      </div>

      {phase === 'idle' && (
        <p className="organs-note">
          Search the brain's L3 semantic memory. Hybrid BM25 + vector + recency,
          scored and ranked.
        </p>
      )}

      {phase === 'searching' && (
        <>
          <div className="organs-skel" aria-hidden="true" />
          <div className="organs-skel" aria-hidden="true" />
        </>
      )}

      {phase === 'offline' && (
        <p className="organs-note organs-note--offline">
          MEMORY SEARCH OFFLINE — AI-OS unreachable.
        </p>
      )}

      {phase === 'empty' && (
        <p className="organs-note">No memories matched “{lastQuery}”.</p>
      )}

      {phase === 'results' && Array.isArray(results) && (
        <div>
          {results.map((hit) => (
            <Row key={hit.id} hit={hit} />
          ))}
        </div>
      )}
    </section>
  );
}
