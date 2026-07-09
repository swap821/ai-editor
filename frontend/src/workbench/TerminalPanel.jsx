import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Terminal, Copy, Trash2, X, ChevronUp } from 'lucide-react';
// import { subscribeCognition } from '../superbrain/lib/cognitionBus';

export default function TerminalPanel() {
  const [isOpen, setIsOpen] = useState(false);
  // Lazy initializer — avoids calling setState synchronously inside an effect
  const [logs, setLogs] = useState(() => [{
    id: Date.now(),
    command: 'gag system start',
    output: 'GAGOS v10 Terminal Online.',
    returncode: 0,
    timestamp: new Date().toISOString()
  }]);
  const bottomRef = useRef(null);
  
  useEffect(() => {
    // Keyboard shortcut to toggle terminal (Ctrl+`)
    const handleKeyDown = (e) => {
      if (e.ctrlKey && e.key === '`') {
        e.preventDefault();
        setIsOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);


  useEffect(() => {
    if (isOpen && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, isOpen]);

  const copyAll = () => {
    const text = logs.map(l => `$ ${l.command}\n${l.output}`).join('\n\n');
    navigator.clipboard.writeText(text);
  };

  const clearAll = () => setLogs([]);

  return (
    <AnimatePresence>
      <div 
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          zIndex: 15,
          pointerEvents: 'none',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        {/* Toggle Tab */}
        {!isOpen && (
          <button
            onClick={() => setIsOpen(true)}
            style={{
              background: 'var(--ag-surface-base)',
              border: 'var(--hairline)',
              borderBottom: 'none',
              borderTopLeftRadius: 'var(--radius-md)',
              borderTopRightRadius: 'var(--radius-md)',
              padding: '4px 16px',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              color: 'var(--text-2)',
              pointerEvents: 'auto',
              cursor: 'pointer',
              backdropFilter: 'var(--ag-blur-md) var(--ag-saturate)',
              WebkitBackdropFilter: 'var(--ag-blur-md) var(--ag-saturate)',
            }}
          >
            <Terminal size={14} />
            <span style={{ fontSize: 'var(--text-xs)' }}>Terminal (Ctrl+`)</span>
            <ChevronUp size={14} />
          </button>
        )}

        {/* Panel */}
        {isOpen && (
          <motion.div
            initial={{ y: '100%', opacity: 0 }}
            animate={{ y: 0, opacity: 1, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] } }}
            exit={{ y: '100%', opacity: 0, transition: { duration: 0.3 } }}
            style={{
              width: '100%',
              height: '35vh',
              background: 'var(--ag-surface-base)',
              borderTop: 'var(--hairline)',
              backdropFilter: 'var(--ag-blur-lg) var(--ag-saturate)',
              WebkitBackdropFilter: 'var(--ag-blur-lg) var(--ag-saturate)',
              pointerEvents: 'auto',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {/* Header */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '8px 16px',
              borderBottom: 'var(--hairline)',
              background: 'rgba(10,11,16,0.5)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-1)' }}>
                <Terminal size={14} />
                <span style={{ fontSize: 'var(--text-sm)' }}>Terminal</span>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <button onClick={copyAll} style={{ background:'transparent', border:'none', color:'var(--text-2)' }} title="Copy All">
                  <Copy size={14} />
                </button>
                <button onClick={clearAll} style={{ background:'transparent', border:'none', color:'var(--text-2)' }} title="Clear">
                  <Trash2 size={14} />
                </button>
                <button onClick={() => setIsOpen(false)} style={{ background:'transparent', border:'none', color:'var(--text-2)' }} title="Close">
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Output Area */}
            <div style={{
              flex: 1,
              overflowY: 'auto',
              padding: '12px 16px',
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-2)',
            }}>
              {logs.map(log => (
                <div key={log.id} style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
                    <span style={{ color: 'var(--terminal-prompt)' }}>$</span>
                    <span style={{ color: 'var(--text-1)' }}>{log.command}</span>
                    <span style={{ color: 'var(--text-3)', fontSize: 'var(--text-xs)', marginLeft: 'auto' }}>
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <div style={{ 
                    color: log.returncode === 0 ? 'var(--terminal-success)' : 'var(--terminal-error)',
                    whiteSpace: 'pre-wrap',
                    paddingLeft: 16
                  }}>
                    {log.output}
                  </div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          </motion.div>
        )}
      </div>
    </AnimatePresence>
  );
}
