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

/**
 * No mock data: the 3D vertebrae overlay starts empty and fills from a real
 * fetch (see fetchInitialFiles below), not hardcoded filenames. The
 * cognition-bus 'file_tree' event this store also listens for is not
 * currently emitted by the backend, so without the fetch this overlay would
 * show permanently fake data instead of real (if approximate) project state.
 */
const initialState: RepoMapState = { activeFiles: [] };

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

const VALID_STATUSES = new Set(['editing', 'verifying', 'approved', 'failed', 'idle']);

// Extract flat files from nested tree
function extractFiles(nodes: any[]): RepoMapNode[] {
  let files: RepoMapNode[] = [];
  for (const node of nodes) {
    if (node.type === 'file') {
      files.push({
        path: node.path,
        name: node.name,
        // The backend's plain REST tree always sends status: "normal" (there
        // is no live per-file editing/verifying/etc. tracking yet) -- only
        // trust a status that's actually one of ours, default to 'idle'
        // otherwise, rather than passing through an unrecognized value.
        status: VALID_STATUSES.has(node.status) ? node.status : 'idle',
        errorCount: node.errorCount || 0,
      });
    } else if (node.children) {
      files = files.concat(extractFiles(node.children));
    }
  }
  return files;
}

/** The GAGOS API base URL (same env var convention as sessionId.ts). */
const AIOS_BASE = (typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_AIOS_URL) || 'http://localhost:8000';

/**
 * One-shot fetch of the real top-level project tree via the existing REST
 * endpoint (the same one FileTree.jsx uses), so the overlay reflects actual
 * repo state instead of the 4 hardcoded mock files it used to ship with.
 * The backend returns only one level with `status: "normal"` always (there
 * is no backend concept of per-file editing/verifying/approved/failed state
 * yet) -- mapped here to 'idle' rather than inventing a fake status.
 */
async function fetchInitialFiles(): Promise<void> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/files/tree`, { credentials: 'include' });
    if (!res.ok) return;
    const tree = await res.json();
    const files = extractFiles(Array.isArray(tree) ? tree : []).slice(0, 12);
    if (files.length) {
      state = { ...state, activeFiles: files };
      notify();
    }
  } catch {
    // Backend unreachable — leave activeFiles empty rather than showing fake data.
  }
}

// Subscribe to cognition bus for live file_tree updates (not currently
// emitted by the backend, but kept for forward-compat — see module docstring).
if (typeof window !== 'undefined') {
  fetchInitialFiles();
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

export function __resetRepoMapForTests(): void {
  state = { activeFiles: [] };
  listeners.clear();
}
