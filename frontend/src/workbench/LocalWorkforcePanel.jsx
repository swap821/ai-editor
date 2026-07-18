import { useMirrorStore } from '../superbrain/lib/mirrorStore';

export default function LocalWorkforcePanel() {
  const mirror = useMirrorStore();
  const workers = mirror.activeWorkers || [];

  return (
    <div className="gagos-panel">
      <h3>Local Workforce</h3>
      {workers.length === 0 ? (
        <p>No active local workers.</p>
      ) : (
        <ul>
          {workers.map((w) => (
            <li key={w.id || Math.random()}>
              <strong>Worker {w.id}</strong>
              <small> - {w.status || 'Active'}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
