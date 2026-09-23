import { parseCouncilMissions, type CouncilMission } from './contracts';
import { ResourceNotice } from './ResourceNotice';
import { useResource } from './resource';
import { guidedTaskStatus, guidedTaskVerification } from './guidedTaskPresentation';

const noTasks = (data: { missions: CouncilMission[] }) => data.missions.length === 0;

export default function GuidedTaskPanel() {
  const resource = useResource('/api/v1/council/missions?limit=100', parseCouncilMissions, noTasks);
  const tasks = resource.data?.missions ?? [];

  return <section className="gagos-panel lm-guided-tasks" aria-label="Tasks">
    <h3>Tasks</h3>
    <p>Recorded tasks stay readable here. If a task needs your permission, GAGOS will ask before the action.</p>
    <ResourceNotice resource={resource} empty="No tasks are recorded yet." />
    {resource.data && <p>{tasks.length} recorded task{tasks.length === 1 ? '' : 's'}.</p>}
    {tasks.length > 0 && <ul>
      {tasks.map((task) => <li key={task.missionId}>
        <h4>{task.mission}</h4>
        <p>{guidedTaskStatus(task)}</p>
        <p>{guidedTaskVerification(task)}</p>
      </li>)}
    </ul>}
  </section>;
}
