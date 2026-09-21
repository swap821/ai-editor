import { useCallback, useState } from 'react';
import HUDPanel from '../components/HUDPanel';
import { Search } from 'lucide-react';
import { ResourceNotice } from '../livingMirror/ResourceNotice';
import { useResource } from '../livingMirror/resource';
import { isRecord } from '../livingMirror/contracts';

const emptyGraph = (graph) => graph.edges.length === 0;

function parseGraph(value, start) {
  if (!isRecord(value) || value.start !== start || !Number.isInteger(value.depth) || value.depth < 1 || value.depth > 4
    || !Array.isArray(value.edges) || !value.edges.every((edge) => isRecord(edge)
      && ['subject', 'predicate', 'object', 'path'].every((key) => typeof edge[key] === 'string')
      && Number.isInteger(edge.depth) && edge.depth >= 1 && edge.depth <= value.depth)) {
    throw new Error('Graph data could not be read. The response does not match the requested graph.');
  }
  return value;
}

export default function StigmergyPanel({ onClose }) {
  const [startNode, setStartNode] = useState('system');
  const [query, setQuery] = useState('system');
  const parse = useCallback((value) => parseGraph(value, query), [query]);
  const resource = useResource(`/api/v1/memory/facts/graph?start=${encodeURIComponent(query)}&depth=2`, parse, emptyGraph);
  const edges = resource.data?.edges ?? [];

  const handleSearch = (e) => {
    e.preventDefault();
    const next = startNode.trim();
    if (!next) return;
    if (next === query) resource.refresh();
    else setQuery(next);
  };

  return (
    <HUDPanel
      id="stigmergy-panel"
      title="Stigmergy Graph"
      tint="cyan"
      defaultPosition={{ x: 50, y: window.innerHeight / 2 }}
      defaultSize={{ width: 350, height: 400 }}
      onClose={onClose}
    >
      <div style={{ padding: '16px', color: 'var(--foreground)', height: '100%', display: 'flex', flexDirection: 'column' }}>
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <div style={{ 
            display: 'flex', 
            flex: 1, 
            alignItems: 'center', 
            background: 'var(--ag-surface-cyan)', 
            border: '1px solid rgba(123, 245, 251, 0.3)',
            borderRadius: '4px',
            padding: '4px 8px'
          }}>
            <Search size={14} style={{ color: 'var(--ag-text-cyan)', marginRight: '8px' }} />
            <input 
              type="text" 
              aria-label="Graph start node"
              value={startNode}
              onChange={(e) => setStartNode(e.target.value)}
              placeholder="Start node..."
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--foreground)',
                fontSize: '12px',
                outline: 'none',
                width: '100%'
              }}
            />
          </div>
          <button type="submit" disabled={!startNode.trim()} style={{
            background: 'rgba(123, 245, 251, 0.1)',
            border: '1px solid var(--ag-glow-cyan)',
            color: 'var(--ag-text-cyan)',
            padding: '4px 12px',
            borderRadius: '4px',
            fontSize: '12px',
            cursor: 'pointer'
          }}>
            Query
          </button>
        </form>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          <ResourceNotice resource={resource} empty={`No edges found for "${query}".`} />
          {resource.data && <p style={{ fontSize: '12px' }}>Graph from "{resource.data.start}" · {resource.data.depth} hops</p>}
          {edges.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {edges.map((edge, idx) => (
                <div key={idx} style={{
                  fontSize: '11px',
                  background: 'rgba(123, 245, 251, 0.05)',
                  padding: '8px',
                  borderRadius: '4px',
                  borderLeft: `2px solid ${edge.depth === 1 ? 'var(--ag-text-cyan)' : 'var(--ag-text-purple)'}`
                }}>
                  <div style={{ color: '#a5f3fc', marginBottom: '4px' }}>
                    <strong>{edge.subject}</strong> <span style={{ color: 'var(--muted-foreground)' }}>{edge.predicate}</span> <strong>{edge.object}</strong>
                  </div>
                  {edge.path && (
                    <div style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
                      Path: {edge.path}
                    </div>
                  )}
                  <div style={{ fontSize: '9px', color: 'var(--muted-foreground)', marginTop: '2px' }}>
                    Depth: {edge.depth}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </HUDPanel>
  );
}
