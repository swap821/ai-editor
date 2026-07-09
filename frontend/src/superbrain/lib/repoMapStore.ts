import { subscribeCognition } from './cognitionBus';

export interface RepoMapNode {
  path: string;
  name: string;
  status: 'editing' | 'verifying' | 'approved' | 'failed' | 'idle';
  errorCount: number;
}

export interface RepoMapState {
  activeFiles: RepoMapNode[];
}

const initialState: RepoMapState = {
  activeFiles: [
    // Mock initial state to show some vertebrae glow
    { path: '/src/main.jsx', name: 'main.jsx', status: 'approved', errorCount: 0 },
    { path: '/src/App.jsx', name: 'App.jsx', status: 'editing', errorCount: 2 },
    { path: '/docs/architecture.md', name: 'architecture.md', status: 'verifying', errorCount: 0 },
    { path: '/docs/README.md', name: 'README.md', status: 'failed', errorCount: 5 },
  ],
};

let state: RepoMapState = { ...initialState };
const listeners = new Set<(state: RepoMapState) => void>();

function notify(): void {
  for (const listener of listeners) listener(state);
}

export function subscribeRepoMap(listener: (state: RepoMapState) => void): () => void {
  listeners.add(listener);
  listener(state);
  return () => listeners.delete(listener);
}

export function getRepoMapState(): RepoMapState {
  return state;
}

// Extract flat files from nested tree
function extractFiles(nodes: any[]): RepoMapNode[] {
  let files: RepoMapNode[] = [];
  for (const node of nodes) {
    if (node.type === 'file') {
      files.push({
        path: node.path,
        name: node.name,
        status: node.status || 'idle',
        errorCount: node.errorCount || 0,
      });
    } else if (node.children) {
      files = files.concat(extractFiles(node.children));
    }
  }
  return files;
}

// Subscribe to cognition bus for file_tree updates
if (typeof window !== 'undefined') {
  subscribeCognition((event) => {
    if (event.type === 'file_tree' && event.data?.tree) {
      const tree = Array.isArray(event.data.tree) ? event.data.tree : [];
      const flatFiles = extractFiles(tree);
      // Sort by status activity (failed, verifying, editing, approved) or error count
      // For now, just take top 12
      state = { ...state, activeFiles: flatFiles.slice(0, 12) };
      notify();
    }
  });
}
