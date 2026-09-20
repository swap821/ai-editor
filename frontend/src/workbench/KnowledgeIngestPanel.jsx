import { useCallback, useEffect, useState } from 'react';
import { Database, FileText, Plus, Search, Trash2 } from 'lucide-react';
import { API_BASE, API_HEADERS } from '../config';

class InvalidKnowledgePayload extends Error {
  constructor(message) {
    super(message);
    this.name = 'InvalidKnowledgePayload';
  }
}

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function finiteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

async function fetchJson(path, signal) {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    credentials: 'include',
    headers: API_HEADERS,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function postMultipart(path, file) {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: API_HEADERS,
    body: form,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function deleteJson(path) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: API_HEADERS,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function parseSourcesPayload(data) {
  if (!isRecord(data) || !Array.isArray(data.sources)) {
    throw new InvalidKnowledgePayload('sources must be an array');
  }

  return data.sources.map((source, index) => {
    if (!isRecord(source) || !Number.isInteger(source.id) || source.id < 1) {
      throw new InvalidKnowledgePayload(`source ${index} is invalid`);
    }
    return {
      id: source.id,
      filename: typeof source.filename === 'string' && source.filename.trim() ? source.filename.trim() : null,
      mimeType: typeof source.mime_type === 'string' && source.mime_type.trim() ? source.mime_type.trim() : null,
      chunkCount: Number.isInteger(source.chunk_count) && source.chunk_count >= 0 ? source.chunk_count : null,
      createdAt: typeof source.created_at === 'string' && source.created_at.trim() ? source.created_at : null,
    };
  });
}

function parseKnowledgeQueryPayload(data) {
  if (!isRecord(data) || typeof data.entity !== 'string' || !Array.isArray(data.edges)) {
    throw new InvalidKnowledgePayload('knowledge query envelope is invalid');
  }
  if (data.inference !== null && !isRecord(data.inference)) {
    throw new InvalidKnowledgePayload('knowledge inference is invalid');
  }

  const edges = data.edges.map((edge, index) => {
    if (
      !isRecord(edge) ||
      typeof edge.subject !== 'string' ||
      typeof edge.predicate !== 'string' ||
      typeof edge.object !== 'string' ||
      !Number.isInteger(edge.depth) ||
      edge.depth < 0 ||
      finiteNumber(edge.confidence) === null ||
      finiteNumber(edge.path_confidence) === null
    ) {
      throw new InvalidKnowledgePayload(`knowledge edge ${index} is invalid`);
    }
    return {
      subject: edge.subject,
      predicate: edge.predicate,
      object: edge.object,
      depth: edge.depth,
      confidence: edge.confidence,
      pathConfidence: edge.path_confidence,
    };
  });

  let inference = null;
  if (data.inference !== null) {
    const raw = data.inference;
    if (
      typeof raw.answer !== 'string' ||
      finiteNumber(raw.confidence) === null ||
      !Number.isInteger(raw.chain_length) ||
      raw.chain_length < 0 ||
      typeof raw.reached_horizon !== 'boolean'
    ) {
      throw new InvalidKnowledgePayload('knowledge inference is invalid');
    }
    inference = {
      answer: raw.answer,
      confidence: raw.confidence,
      chainLength: raw.chain_length,
      reachedHorizon: raw.reached_horizon,
    };
  }

  return { entity: data.entity, edges, inference };
}

function scoreLabel(score) {
  return finiteNumber(score) === null ? 'Score unavailable' : `Score: ${Math.round(score * 100)}%`;
}

function confidenceLabel(score) {
  return finiteNumber(score) === null ? 'Confidence unavailable' : `${Math.round(score * 100)}%`;
}

export default function KnowledgeIngestPanel() {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [ingestType, setIngestType] = useState('file');
  const [ingestFile, setIngestFile] = useState(null);
  const [ingestText, setIngestText] = useState('');
  const [ingestBusy, setIngestBusy] = useState(false);
  const [ingestError, setIngestError] = useState('');

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState('');

  const loadSources = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchJson('/api/v1/knowledge/sources', signal);
      setSources(parseSourcesPayload(data));
    } catch (err) {
      if (err?.name !== 'AbortError') {
        setError(err?.name === 'InvalidKnowledgePayload' ? 'Knowledge sources unavailable' : 'Knowledge base offline');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void loadSources(ctrl.signal);
    return () => ctrl.abort();
  }, [loadSources]);

  const handleIngest = async (e) => {
    e.preventDefault();
    setIngestBusy(true);
    setIngestError('');
    try {
      const file = ingestType === 'file'
        ? ingestFile
        : new File([ingestText], 'operator-notes.txt', { type: 'text/plain' });
      if (!file || (ingestType === 'text' && !ingestText.trim())) {
        setIngestError(ingestType === 'file' ? 'Choose a document before ingesting.' : 'Enter text before ingesting.');
        return;
      }
      await postMultipart('/api/v1/knowledge/ingest', file);
      setIngestFile(null);
      setIngestText('');
      void loadSources();
    } catch (err) {
      setIngestError('Ingestion failed: ' + err.message);
    } finally {
      setIngestBusy(false);
    }
  };

  const handleDeleteSource = async (id) => {
    if (!window.confirm('Remove this knowledge source?')) return;
    try {
      await deleteJson(`/api/v1/knowledge/sources/${encodeURIComponent(id)}`);
      void loadSources();
    } catch (err) {
      alert('Could not delete source');
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearchBusy(true);
    setSearchError('');
    setSearchResults(null);
    try {
      const data = await fetchJson(`/api/v1/knowledge/query?entity=${encodeURIComponent(searchQuery.trim())}`);
      setSearchResults(parseKnowledgeQueryPayload(data));
    } catch (err) {
      setSearchError(err?.name === 'InvalidKnowledgePayload' ? 'Knowledge graph unavailable' : 'Knowledge graph offline');
    } finally {
      setSearchBusy(false);
    }
  };

  return (
    <div className="council-dashboard__body" aria-label="Knowledge Ingestion">
      <div className="council-dashboard__detail">
        <section className="council-dashboard__section">
          <h3>
            <Database size={14} aria-hidden="true" /> Active Knowledge Sources
          </h3>
          {loading ? (
            <p className="council-dashboard__muted">Loading sources...</p>
          ) : error ? (
            <p className="council-dashboard__error">{error}</p>
          ) : sources.length === 0 ? (
            <p className="council-dashboard__muted">No knowledge sources ingested yet.</p>
          ) : (
            sources.map((src) => (
              <div key={src.id} className="council-dashboard__route">
                <span>
                  <FileText size={12} aria-hidden="true" />{' '}
                  {src.filename || `Source #${src.id}`}
                </span>
                <span className="council-dashboard__muted">
                  {src.chunkCount === null ? 'Chunk count unavailable' : `${src.chunkCount} chunks`}
                </span>
                <button type="button" onClick={() => handleDeleteSource(src.id)} aria-label="Delete source">
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </section>

        <section className="council-dashboard__section">
          <h3>
            <Plus size={14} aria-hidden="true" /> Ingest New Knowledge
          </h3>
          <div className="council-dashboard__tabs" style={{ marginBottom: '8px' }}>
            <button
              type="button"
              className={`council-dashboard__tab${ingestType === 'file' ? ' is-active' : ''}`}
              onClick={() => setIngestType('file')}
            >
              Document File
            </button>
            <button
              type="button"
              className={`council-dashboard__tab${ingestType === 'text' ? ' is-active' : ''}`}
              onClick={() => setIngestType('text')}
            >
              Raw Text
            </button>
          </div>
          <form className="council-dashboard__originate" onSubmit={handleIngest}>
            {ingestType === 'file' ? (
              <input
                type="file"
                className="council-dashboard__origin-files"
                accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
                onChange={(e) => setIngestFile(e.target.files?.[0] ?? null)}
                aria-label="Knowledge document file"
                required
              />
            ) : (
              <textarea
                className="council-dashboard__origin-goal"
                value={ingestText}
                onChange={(e) => setIngestText(e.target.value)}
                placeholder="Paste raw documentation or facts..."
                rows={4}
                required
              />
            )}
            {ingestError ? <p className="council-dashboard__error">{ingestError}</p> : null}
            <button type="submit" disabled={ingestBusy}>
              {ingestBusy ? 'Ingesting...' : 'Ingest Data'}
            </button>
          </form>
        </section>

        <section className="council-dashboard__section">
          <h3>
            <Search size={14} aria-hidden="true" /> Test Knowledge Graph Query
          </h3>
          <form className="council-dashboard__originate" onSubmit={handleSearch}>
            <input
              type="text"
              className="council-dashboard__origin-files"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Query the knowledge base..."
              required
            />
            {searchError ? <p className="council-dashboard__error">{searchError}</p> : null}
            <button type="submit" disabled={searchBusy}>
              {searchBusy ? 'Searching...' : 'Search'}
            </button>
          </form>

          {searchResults !== null && (
            <div className="council-dashboard__verdicts" style={{ marginTop: '16px' }}>
              {searchResults.edges.length === 0 && searchResults.inference === null ? (
                <p className="council-dashboard__muted">No matching context found.</p>
              ) : (
                <>
                  {searchResults.inference ? (
                    <div className="council-dashboard__route" style={{ display: 'block', padding: '8px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <strong className="council-dashboard__badge is-ok">{scoreLabel(searchResults.inference.confidence)}</strong>
                        <span className="council-dashboard__muted">{searchResults.inference.chainLength} hop(s)</span>
                      </div>
                      <p style={{ margin: 0, fontSize: '0.85em', whiteSpace: 'pre-wrap' }}>{searchResults.inference.answer}</p>
                    </div>
                  ) : null}
                  {searchResults.edges.map((edge, i) => (
                    <div key={`${edge.subject}-${edge.predicate}-${edge.object}-${i}`} className="council-dashboard__route" style={{ display: 'block', padding: '8px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <strong>{edge.subject} {edge.predicate} {edge.object}</strong>
                        <span className="council-dashboard__muted">Confidence: {confidenceLabel(edge.confidence)}</span>
                      </div>
                      <p style={{ margin: 0, fontSize: '0.8em' }}>Path confidence: {confidenceLabel(edge.pathConfidence)}</p>
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
