import HUDPanel from '../components/HUDPanel';
import { API_HEADERS } from '../config';
import { ResourceNotice } from '../livingMirror/ResourceNotice';
import { useResource } from '../livingMirror/resource';
import './MemoryBrowser.css';

const experienceRead = Object.freeze({
  method: 'POST',
  headers: { 'Content-Type': 'application/json', ...API_HEADERS },
  body: JSON.stringify({ path: '.aios/memory/experiences.jsonl' }),
});

function asText(value) {
  return typeof value === 'string' && value.trim() ? value : null;
}

function parseExperienceFile(value) {
  if (!value || typeof value !== 'object' || typeof value.content !== 'string') {
    throw new Error('The experience ledger response is incomplete.');
  }

  const records = [];
  const malformedLines = [];
  for (const [index, line] of value.content.split(/\r?\n/).entries()) {
    if (!line.trim()) continue;
    try {
      const parsed = JSON.parse(line);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('record is not an object');
      records.push({
        id: asText(parsed.task_id) || `line-${index + 1}`,
        taskId: asText(parsed.task_id),
        timestamp: asText(parsed.ts),
        goal: asText(parsed.goal),
        plan: asText(parsed.plan),
        actions: Array.isArray(parsed.actions) ? parsed.actions.filter((action) => typeof action === 'string') : [],
        outcome: asText(parsed.outcome),
        failureModes: asText(parsed.failure_modes),
        fixes: asText(parsed.fixes),
        lessons: asText(parsed.lessons),
        confidence: typeof parsed.confidence === 'number' && Number.isFinite(parsed.confidence) ? parsed.confidence : null,
      });
    } catch {
      malformedLines.push(index + 1);
    }
  }
  return { records: records.reverse(), malformedLines };
}

const emptyExperiences = (data) => data.records.length === 0 && data.malformedLines.length === 0;

function outcomeClass(outcome) {
  if (/\bsuccess(?:ful)?\b/i.test(outcome || '')) return 'is-ok';
  if (/\bfail(?:ure|ed)?\b/i.test(outcome || '')) return 'is-danger';
  return 'is-warn';
}

function formatTimestamp(timestamp) {
  if (!timestamp) return 'Time unavailable';
  const parsed = new Date(timestamp);
  return Number.isNaN(parsed.getTime()) ? timestamp : parsed.toLocaleString();
}

function ExperienceRecord({ experience }) {
  return (
    <article className="memory-browser__record">
      <header className="memory-browser__record-header">
        <strong>{experience.taskId || 'Unidentified experience'}</strong>
        <time dateTime={experience.timestamp || undefined}>{formatTimestamp(experience.timestamp)}</time>
      </header>

      {experience.goal ? <p><b>Goal</b>{experience.goal}</p> : null}
      {experience.outcome ? <p><b>Outcome</b><span className={`memory-browser__outcome ${outcomeClass(experience.outcome)}`}>{experience.outcome}</span></p> : null}
      {experience.lessons ? <p><b>Lesson</b>{experience.lessons}</p> : null}
      {experience.confidence !== null ? <p><b>Confidence</b>{Math.round(experience.confidence * 100)}%</p> : null}

      {(experience.plan || experience.actions.length || experience.failureModes || experience.fixes) ? (
        <details>
          <summary>Inspect the recorded path</summary>
          <dl>
            {experience.plan ? <><dt>Plan</dt><dd>{experience.plan}</dd></> : null}
            {experience.actions.length ? <><dt>Actions</dt><dd><ol>{experience.actions.map((action, index) => <li key={`${experience.id}-action-${index}`}>{action}</li>)}</ol></dd></> : null}
            {experience.failureModes ? <><dt>Failure modes</dt><dd>{experience.failureModes}</dd></> : null}
            {experience.fixes ? <><dt>Fixes</dt><dd>{experience.fixes}</dd></> : null}
          </dl>
        </details>
      ) : null}
    </article>
  );
}

export default function MemoryBrowser({ onClose }) {
  const resource = useResource('/api/v1/files/read', parseExperienceFile, emptyExperiences, experienceRead);
  const records = resource.data?.records ?? [];
  const malformedLines = resource.data?.malformedLines ?? [];

  return (
    <HUDPanel
      id="memory-browser"
      title="Memory Browser"
      tint="purple"
      defaultPosition={{ x: window.innerWidth / 2 - 250, y: window.innerHeight / 2 - 200 }}
      defaultSize={{ width: 500, height: 400 }}
      onClose={onClose}
    >
      <div className="memory-browser" aria-label="Durable experience ledger">
        <h3>Experience accumulator</h3>
        <p className="memory-browser__intro">Recorded experience remains inspectable before it can influence future work.</p>
        <ResourceNotice resource={resource} empty="The durable experience ledger is empty." />
        {malformedLines.length ? (
          <p className="memory-browser__warning" role="alert">
            {malformedLines.length} ledger line{malformedLines.length === 1 ? '' : 's'} could not be parsed; valid records remain visible.
          </p>
        ) : null}
        {records.length ? (
          <div className="memory-browser__records">
            {records.map((experience) => <ExperienceRecord key={experience.id} experience={experience} />)}
          </div>
        ) : null}
      </div>
    </HUDPanel>
  );
}
