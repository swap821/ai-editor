import { parseSkills } from '../livingMirror/contracts';
import { useResource } from '../livingMirror/resource';
import { ResourceNotice } from '../livingMirror/ResourceNotice';
import { SkillActions } from '../livingMirror/SkillActions';

const emptySkills = (data) => data.items.length === 0;

export default function SkillLibraryPanel() {
  const resource = useResource('/api/v1/skills', parseSkills, emptySkills);
  const skills = resource.data?.items ?? [];

  return (
    <div className="gagos-panel">
      <h3>Experience & skills</h3>
      <p>Recorded experience becomes reusable only within its applicability and authority limits.</p>
      <ResourceNotice resource={resource} empty="The durable repository contains no skill versions." />
      {skills.length > 0 && (
        <ul>
          {skills.map((s) => (
            <li key={`${s.skill_id}:${s.version}`}>
              <strong>{s.problem_signature}</strong>
              <p><code>{s.skill_id}</code> · Version {s.version} · {s.state.replaceAll('_', ' ')}</p>
              <details>
                <summary>Applicability, procedure & lineage</summary>
                <dl>
                  <dt>Applicability</dt><dd>{Object.entries(s.applicability_conditions).map(([k, v]) => `${k}: ${v}`).join('; ') || 'No conditions recorded'}</dd>
                  <dt>Exclusions</dt><dd>{s.known_exclusions.join(', ') || 'None recorded'}</dd>
                  <dt>Required inputs</dt><dd>{s.required_inputs.join(', ') || 'None recorded'}</dd>
                  <dt>Required project state</dt><dd>{Object.entries(s.required_project_state).map(([k, v]) => `${k}: ${v}`).join('; ') || 'None recorded'}</dd>
                  <dt>Procedure</dt><dd>{s.procedure}</dd>
                  <dt>Scope</dt><dd><code>{s.allowed_scope_pattern}</code></dd>
                  <dt>Tools</dt><dd>{s.allowed_tools.join(', ') || 'None recorded'}</dd>
                  <dt>Source trajectories</dt><dd>{s.source_trajectory_ids.join(', ') || 'Unavailable'}</dd>
                  <dt>Recorded reuse outcomes</dt><dd>{s.success_count} successes; {s.failure_count} failures</dd>
                  <dt>Escalation</dt><dd>{s.escalation_conditions.join('; ') || 'None recorded'}</dd>
                </dl>
                {s.verification_plan ? <details><summary>Verification specification</summary><pre>{JSON.stringify(s.verification_plan, null, 2)}</pre></details> : <p>Verification specification unavailable.</p>}
              </details>
              <SkillActions skill={s} available={resource.status === 'available'} refresh={resource.refresh} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
