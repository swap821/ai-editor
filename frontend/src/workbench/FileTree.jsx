import React, { useState, useEffect, useMemo, useRef } from 'react';
import HUDPanel from '../components/HUDPanel';
import { ChevronRight, ChevronDown, File as FileIcon, Folder, FolderOpen, Search, Sparkles } from 'lucide-react';

const Badge = ({ type }) => {
  const colors = {
    editing: 'var(--tree-badge-edit, #7bf5fb)',
    verifying: 'var(--tree-badge-verify, #fbbf24)',
    approved: 'var(--tree-badge-approve, #34d399)',
    failed: 'var(--tree-badge-fail, #f87171)',
  };
  
  if (!type || !colors[type]) return null;
  
  return (
    <div
      style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        backgroundColor: colors[type],
        marginLeft: 8,
        boxShadow: `0 0 8px ${colors[type]}`,
      }}
      title={`Status: ${type}`}
    />
  );
};

const FileNode = ({ node, level, onSelect, expanded, toggleExpand, searchQuery, onRightClick }) => {
  const isDir = node.type === 'directory';
  const isExpanded = expanded[node.path];
  const paddingLeft = level * 16 + 8;
  
  const matchesSearch = searchQuery && node.name.toLowerCase().includes(searchQuery.toLowerCase());
  const hasMatchingChild = useMemo(() => {
    if (!searchQuery || !isDir) return false;
    const checkMatch = (n) => {
      if (n.name.toLowerCase().includes(searchQuery.toLowerCase())) return true;
      if (n.children) return n.children.some(checkMatch);
      return false;
    };
    return node.children?.some(checkMatch);
  }, [node, searchQuery, isDir]);

  if (searchQuery && !matchesSearch && !hasMatchingChild) {
    return null;
  }

  return (
    <React.Fragment>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: `4px 8px 4px ${paddingLeft}px`,
          cursor: 'pointer',
          color: matchesSearch ? 'var(--neon-cyan)' : 'var(--text-2)',
          backgroundColor: 'transparent',
        }}
        onClick={() => {
          if (isDir) toggleExpand(node.path);
          else onSelect(node);
        }}
        onContextMenu={(e) => {
          e.preventDefault();
          onRightClick(node, e);
        }}
        onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--tree-hover)'; }}
        onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
      >
        {isDir ? (
          <span style={{ marginRight: 4, display: 'flex', alignItems: 'center' }}>
            {isExpanded || hasMatchingChild ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {isExpanded || hasMatchingChild ? <FolderOpen size={14} style={{ marginLeft: 4, color: 'var(--neon-purple)' }} /> : <Folder size={14} style={{ marginLeft: 4, color: 'var(--neon-cyan)' }} />}
          </span>
        ) : (
          <span style={{ marginRight: 4, display: 'flex', alignItems: 'center', marginLeft: 18 }}>
            <FileIcon size={14} />
          </span>
        )}
        <span style={{ fontSize: 'var(--text-sm)', userSelect: 'none', marginLeft: 4 }}>
          {node.name}
        </span>
        <Badge type={node.status} />
      </div>
      
      {(isExpanded || hasMatchingChild) && isDir && node.children && (
        <div>
          {node.children.map(child => (
            <FileNode
              key={child.path}
              node={child}
              level={level + 1}
              onSelect={onSelect}
              expanded={expanded}
              toggleExpand={toggleExpand}
              searchQuery={searchQuery}
              onRightClick={onRightClick}
            />
          ))}
        </div>
      )}
    </React.Fragment>
  );
};

export default function FileTree({ onClose, onOpenFile }) {
  const [treeData, setTreeData] = useState([]);
  const [expanded, setExpanded] = useState({});
  const [searchQuery, setSearchQuery] = useState('');
  const [contextMenu, setContextMenu] = useState(null);
  const containerRef = useRef(null);

  useEffect(() => {
    // Mock fetch for now, replace with actual fetch when backend is ready
    const fetchTree = async () => {
      try {
        // const response = await fetch('/api/v1/files/tree');
        // const data = await response.json();
        const data = [
          {
            name: 'src', path: '/src', type: 'directory', children: [
              { name: 'main.jsx', path: '/src/main.jsx', type: 'file', status: 'approved' },
              { name: 'App.jsx', path: '/src/App.jsx', type: 'file', status: 'editing' }
            ]
          },
          {
            name: 'docs', path: '/docs', type: 'directory', children: [
              { name: 'architecture.md', path: '/docs/architecture.md', type: 'file', status: 'verifying' },
              { name: 'README.md', path: '/docs/README.md', type: 'file', status: 'failed' }
            ]
          }
        ];
        setTreeData(data);
        
        // Auto-expand root directories
        const initialExpanded = {};
        data.forEach(n => { initialExpanded[n.path] = true; });
        setExpanded(initialExpanded);
      } catch (e) {
        console.error('Failed to fetch file tree', e);
      }
    };
    fetchTree();
  }, []);

  const toggleExpand = (path) => {
    setExpanded(prev => ({ ...prev, [path]: !prev[path] }));
  };

  const handleRightClick = (node, e) => {
    setContextMenu({
      node,
      x: e.clientX,
      y: e.clientY
    });
  };

  // Close context menu on outside click
  useEffect(() => {
    const handleClick = () => setContextMenu(null);
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, []);

  return (
    <HUDPanel
      title="File Tree"
      tint="cyan"
      defaultPosition={{ x: 20, y: 100 }}
      defaultSize={{ width: 280, height: 500 }}
      onClose={onClose}
    >
      <div style={{ padding: '8px', borderBottom: 'var(--hairline)' }}>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
          <Search size={14} style={{ position: 'absolute', left: 8, color: 'var(--text-3)' }} />
          <input
            type="text"
            placeholder="Search files..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              background: 'rgba(0,0,0,0.2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '4px 8px 4px 28px',
              color: 'var(--text-1)',
              fontSize: 'var(--text-sm)',
              outline: 'none',
            }}
          />
        </div>
      </div>
      
      <div ref={containerRef} style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {treeData.map(node => (
          <FileNode
            key={node.path}
            node={node}
            level={0}
            onSelect={onOpenFile}
            expanded={expanded}
            toggleExpand={toggleExpand}
            searchQuery={searchQuery}
            onRightClick={handleRightClick}
          />
        ))}
      </div>

      {contextMenu && (
        <div
          style={{
            position: 'fixed',
            top: contextMenu.y,
            left: contextMenu.x,
            background: 'var(--surface-3)',
            border: 'var(--hairline)',
            borderRadius: 'var(--radius-sm)',
            boxShadow: 'var(--elevation-3)',
            padding: '4px',
            zIndex: 100,
          }}
        >
          <button
            onClick={() => {
              console.log('Asking GAGOS to edit', contextMenu.node.path);
              setContextMenu(null);
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              background: 'transparent',
              border: 'none',
              padding: '6px 12px',
              color: 'var(--neon-cyan)',
              width: '100%',
              textAlign: 'left',
              fontSize: 'var(--text-sm)',
              borderRadius: 'var(--radius-xs)',
              cursor: 'pointer',
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = 'var(--tree-active)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
          >
            <Sparkles size={14} />
            Ask GAGOS to edit this
          </button>
        </div>
      )}
    </HUDPanel>
  );
}
