import { useMirrorStore } from '../superbrain/lib/mirrorStore';
import { parseCouncilMissions } from '../livingMirror/contracts';
import { useResource } from '../livingMirror/resource';
import { ResourceNotice } from '../livingMirror/ResourceNotice';
import { MissionInspector } from '../livingMirror/MissionInspector';
import { useTabStore, selectMission } from '../superbrain/lib/tabStore';

const noMissions = (data) => data.missions.length === 0;

export default function MissionControlPanel() {
  const mirror = useMirrorStore();
  const { selectedMissionId: selectedId } = useTabStore();
  const resource = useResource('/api/v1/council/missions?limit=100', parseCouncilMissions, noMissions);
  const missions = resource.data?.missions ?? [];
  const otherIds = mirror.activeMissions.filter((id) => !missions.some((m) => m.missionId === id));

  return (
    <div className="gagos-panel">
      <h3>Missions</h3>
      <p>Council reports are one mission family. Live mission IDs without a Council report remain visible below.</p>
      <ResourceNotice resource={resource} empty="No readable Council reports were returned." />
      {resource.data && <p>{missions.length} of {resource.data.count} readable reports</p>}
      {missions.length > 0 && (
        <ul>
          {missions.map((m) => (
            <li key={m.missionId}>
              <button type="button" aria-expanded={selectedId === m.missionId} onClick={() => selectMission(selectedId === m.missionId ? null : m.missionId)}>{m.mission}</button>
              <p><code>{m.missionId}</code> · Report: {m.status}</p>
              {selectedId === m.missionId && <MissionInspector id={m.missionId} />}
            </li>
          ))}
        </ul>
      )}
      {otherIds.length > 0 && <ul>{otherIds.map((id) => <li key={id}><code>{id}</code><p>Observed active mission; Council detail unavailable.</p></li>)}</ul>}
    </div>
  );
}
