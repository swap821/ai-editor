import { useState, useEffect } from 'react';
import HUDPanel from '../components/HUDPanel';
import { Search } from 'lucide-react';

export default function StigmergyPanel({ onClose }) {
  const [startNode, setStartNode] = useState('system');
  const [edges, setEdges] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchGraph = async (node) => {
    if (!node.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/memory/facts/graph?start=${encodeURIComponent(node)}&depth=2`);
      if (!response.ok) {
        throw new Error('Failed to fetch graph');
      }
      const data = await response.json();
      setEdges(data.edges || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGraph(startNode);
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchGraph(startNode);
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
          <button type="submit" style={{
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
          {loading ? (
            <div style={{ fontSize: '12px', opacity: 0.6 }}>Traversing lattice...</div>
          ) : error ? (
            <div style={{ fontSize: '12px', color: 'var(--ag-text-amber)' }}>Error: {error}</div>
          ) : edges.length === 0 ? (
            <div style={{ fontSize: '12px', opacity: 0.6 }}>No edges found for "{startNode}".</div>
          ) : (
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
