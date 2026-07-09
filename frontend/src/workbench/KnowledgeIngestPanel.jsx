import { useCallback, useEffect, useState } from 'react';
import { Database, Plus, Search, Trash2, Link as LinkIcon, FileText } from 'lucide-react';
import { API_BASE, API_HEADERS } from '../config';

async function fetchJson(path, signal) {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    credentials: 'include',
    headers: API_HEADERS,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function postJson(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify(body ?? {}),
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

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

export default function KnowledgeIngestPanel() {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  const [ingestType, setIngestType] = useState('url'); // 'url', 'text'
  const [ingestUrl, setIngestUrl] = useState('');
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
      setSources(asArray(data.sources));
    } catch (err) {
      if (err?.name !== 'AbortError') setError('Knowledge base offline');
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
      const body = ingestType === 'url' ? { url: ingestUrl } : { text: ingestText };
      await postJson('/api/v1/knowledge/ingest', body);
      setIngestUrl('');
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
    try {
      // It's a GET, but we'll use URL params
      const data = await fetchJson(`/api/v1/knowledge/query?q=${encodeURIComponent(searchQuery)}`);
      setSearchResults(asArray(data.results));
    } catch (err) {
      setSearchError('Query failed');
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
            sources.map(src => (
              <div key={src.id} className="council-dashboard__route">
                <span>
                  {src.type === 'url' ? <LinkIcon size={12}/> : <FileText size={12}/>}
                  {' '}
                  {src.title || src.url || `Text Source #${src.id.substring(0,6)}`}
                </span>
                <span className="council-dashboard__muted">{src.chunks} chunks</span>
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
              className={`council-dashboard__tab${ingestType === 'url' ? ' is-active' : ''}`}
              onClick={() => setIngestType('url')}
            >
              URL
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
            {ingestType === 'url' ? (
              <input
                type="url"
                className="council-dashboard__origin-files"
                value={ingestUrl}
                onChange={(e) => setIngestUrl(e.target.value)}
                placeholder="https://docs.example.com"
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
            <Search size={14} aria-hidden="true" /> Test RAG Query
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
              {searchResults.length === 0 ? (
                <p className="council-dashboard__muted">No matching context found.</p>
              ) : (
                searchResults.map((res, i) => (
                  <div key={i} className="council-dashboard__route" style={{ display: 'block', padding: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <strong className="council-dashboard__badge is-ok">Score: {Math.round(res.score * 100)}%</strong>
                      <span className="council-dashboard__muted">{res.source_id?.substring(0, 8)}</span>
                    </div>
                    <p style={{ margin: 0, fontSize: '0.85em', whiteSpace: 'pre-wrap' }}>{res.text}</p>
                  </div>
                ))
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
