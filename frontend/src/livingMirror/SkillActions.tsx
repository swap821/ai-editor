import { useState } from 'react';
import { isRecord, type SkillContract } from './contracts';
import { sendGuardedCommand } from './commands';
import { openWorkspacePanel, selectMission } from '../superbrain/lib/tabStore';

const parseMap = (text: string): Record<string, string> => {
  const value: unknown = JSON.parse(text);
  if (!isRecord(value) || !Object.values(value).every((v) => typeof v === 'string')) throw new Error('Inputs and project state must be JSON objects with string values.');
  return value as Record<string, string>;
};
export function SkillActions({ skill, available, refresh }: { skill: SkillContract; available: boolean; refresh: () => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [goal, setGoal] = useState('');
  const [projectId, setProject] = useState('');
  const [scope, setScope] = useState('');
  const [inputs, setInputs] = useState('{}');
  const [projectState, setProjectState] = useState('{}');
  const [validatedVersion, setVersion] = useState('');
  const [tools, setTools] = useState('');
  const [missionId, setMission] = useState<string | null>(null);
  async function activate() {
    if (!available || busy || !reviewed || skill.state !== 'candidate') return;
    setBusy(true);
    try {
      const result = await sendGuardedCommand(`/api/v1/skills/${encodeURIComponent(skill.skill_id)}/versions/${skill.version}/activate`, {});
      setMessage(result.status === 'accepted' && result.data?.status === 'activated' ? `Version ${skill.version} activation recorded. Refreshing its lifecycle.` : result.message);
    } finally { setBusy(false); setReviewed(false); refresh(); }
  }
  async function reuse() {
    if (!available || busy || !goal.trim() || !projectId.trim() || !scope.trim() || !validatedVersion.trim()) return;
    let body;
    try {
      body = { skill_id: skill.skill_id, version: skill.version, mission_id: `reuse-${crypto.randomUUID()}`, goal: goal.trim(), project_id: projectId.trim(),
        current_scope: scope.trim(), current_inputs: parseMap(inputs), current_state: parseMap(projectState), validated_version: validatedVersion.trim(),
        mission_allowed_tools: tools.split(',').map((tool) => tool.trim()).filter(Boolean) };
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Invalid inputs'); return; }
    setBusy(true); setMission(null);
    try {
      const result = await sendGuardedCommand('/api/v1/skills/reuse', body);
      if (result.status === 'accepted' && result.data?.status === 'mission_created') {
        setMission(body.mission_id); setMessage('Governed mission draft created. Approval and execution remain separate.');
      } else if (result.status === 'accepted' && result.data?.status === 'escalate') setMessage(`Reuse escalated: ${String(result.data.reason ?? 'applicability not established')}`);
      else setMessage(result.message);
    } finally { setBusy(false); refresh(); }
  }
  return <div className="lm-skill-actions">
    {skill.state === 'candidate' && <><label className="lm-check"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} />I reviewed this version's applicability, exclusions and source trajectories.</label>
      <button type="button" disabled={!available || busy || !reviewed} onClick={() => void activate()}>Activate version {skill.version}</button></>}
    <details><summary>Create a governed reuse draft</summary>
      <p>The backend checks applicability and records the outcome, including a mismatch. Creating a draft does not execute or promote work.</p>
      <form className="lm-form" onSubmit={(event) => { event.preventDefault(); void reuse(); }}>
        <label>Goal<input required value={goal} onChange={(event) => setGoal(event.target.value)} /></label>
        <label>Enrolled project ID<input required value={projectId} onChange={(event) => setProject(event.target.value)} /></label>
        <label>Current scope<input required value={scope} onChange={(event) => setScope(event.target.value)} /></label>
        <label>Validated project version<input required value={validatedVersion} onChange={(event) => setVersion(event.target.value)} /></label>
        <label>Allowed tools, comma separated<input value={tools} onChange={(event) => setTools(event.target.value)} /></label>
        <label>Current inputs (JSON)<textarea rows={3} value={inputs} onChange={(event) => setInputs(event.target.value)} /></label>
        <label>Current project state (JSON)<textarea rows={3} value={projectState} onChange={(event) => setProjectState(event.target.value)} /></label>
        <button type="submit" disabled={!available || busy}>Create governed draft</button>
      </form>
    </details>
    {busy && <p role="status">Request pending…</p>}
    {message && <p role="status">{message}</p>}
    {missionId && <p>Draft <code>{missionId}</code>. Generic draft detail is not exposed by the current backend; it may not have a Council report.
      <button type="button" onClick={() => { selectMission(missionId); openWorkspacePanel('missions', 'Missions'); }}>Inspect missions</button></p>}
  </div>;
}
