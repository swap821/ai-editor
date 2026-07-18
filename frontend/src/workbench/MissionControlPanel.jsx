import { useMirrorStore } from '../superbrain/lib/mirrorStore';

export default function MissionControlPanel() {
  const mirror = useMirrorStore();
  const missions = mirror.activeMissions || [];

  return (
    <div className="gagos-panel">
      <h3>Mission Control</h3>
      {missions.length === 0 ? (
        <p>No active missions.</p>
      ) : (
        <ul>
          {missions.map((m) => (
            <li key={m.id || Math.random()}>
              <strong>{m.id}</strong>
              <p>{m.summary || m.goal}</p>
              <small>Status: {m.status}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
