import type { Resource } from './resource';

export function ResourceNotice({ resource, empty }: { resource: Resource<unknown> & { refresh: () => void }; empty: string }) {
  const stale = resource.data !== null && !['available', 'empty'].includes(resource.status);
  return <div className="lm-resource" role="status">
    {resource.status === 'loading' && <span>{stale ? 'Refreshing last-known records…' : 'Loading records…'}</span>}
    {resource.status === 'empty' && <span>{empty}</span>}
    {resource.error && <span>{resource.error} {stale ? 'The records below are last-known.' : ''}</span>}
    {resource.receivedAt && <small>Received {new Date(resource.receivedAt).toLocaleString()}{stale ? ' · stale' : ''}</small>}
    <button type="button" onClick={resource.refresh} disabled={resource.status === 'loading'}>Refresh</button>
  </div>;
}
