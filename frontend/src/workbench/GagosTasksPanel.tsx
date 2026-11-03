import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useResource } from '../livingMirror/resource';
import { ResourceNotice } from '../livingMirror/ResourceNotice';
import { identifiedRecords, noRecords, textValue } from '../livingMirror/recordCollections';
import { sendGuardedCommand } from '../livingMirror/commands';
import { isRecord } from '../livingMirror/contracts';
import './GagosTasksPanel.css';

/**
 * Tasks the operator writes (2026-11-03: "bigger work" for GAGOS): a change in
 * plain words on one file. GAGOS's writers make it, the sandbox runs its
 * tests, Claude Code reviews it, GAGOS opens its own PR, and he merges. The
 * counter serves GET/POST /api/gagos/tasks and POST .../{id}/cancel; this is
 * its face. The task row also carries who said it; that is never shown.
 */
const MAX_TASK_CHARS = 4000;
const POLL_MS = 60_000;
const COLLAPSED_LINES = 3;

type Rec = Record<string, unknown>;
const parseTasks = (value: unknown): Rec[] => {
  if (!isRecord(value) || !Array.isArray(value.tasks)) throw new Error('Unsupported tasks response.');
  return identifiedRecords(value.tasks, 'task_id');
};

const asText = (value: unknown): string => (typeof value === 'string' ? value : '');
const asRec = (value: unknown): Rec | null => (isRecord(value) ? value : null);

/** Only an https link is offered as a link; anything else is shown as plain text. */
const isSafeLink = (url: string) => /^https:\/\//i.test(url);

function rejectionText(result: { message: string; data: Rec | null }): string {
  const detail = result.data?.detail;
  return typeof detail === 'string' && detail ? detail : result.message;
}

function TaskText({ text }: { text: string }) {
  const lines = text.split('\n');
  if (lines.length <= COLLAPSED_LINES) return <p className="gagos-tasks__text">{text}</p>;
  return (
    <details className="gagos-tasks__more">
      <summary>
        <span className="gagos-tasks__text">{lines.slice(0, COLLAPSED_LINES).join('\n')}</span>
        <span> (show all {lines.length} lines)</span>
      </summary>
      <p className="gagos-tasks__text">{text}</p>
    </details>
  );
}

function Progress({ proposal }: { proposal: Rec }) {
  const reviews = asRec(proposal.reviews) ?? {};
  const sandbox = proposal.sandbox;
  const refusal = asText(proposal.refusal);
  const prUrl = asText(proposal.pr_url);
  return (
    <dl className="gagos-tasks__progress">
      <div><dt>Proposal</dt><dd>{textValue(proposal.status)}{refusal ? ` — ${refusal}` : ''}</dd></div>
      <div><dt>Writer</dt><dd>{textValue(proposal.model)}</dd></div>
      <div><dt>Sandbox</dt><dd>{typeof sandbox === 'string' && sandbox ? sandbox : 'not run yet'}</dd></div>
      {Object.entries(reviews).map(([reviewer, review]) => {
        const r = asRec(review) ?? {};
        return (
          <div key={reviewer}>
            <dt>Review by {reviewer}</dt>
            <dd>{textValue(r.verdict)}{asText(r.reason) ? ` — ${asText(r.reason)}` : ''}</dd>
          </div>
        );
      })}
      {Object.keys(reviews).length === 0 && <div><dt>Review</dt><dd>not reviewed yet</dd></div>}
      <div>
        <dt>Pull request</dt>
        <dd>
          {prUrl && isSafeLink(prUrl)
            ? <a href={prUrl} target="_blank" rel="noopener noreferrer">{prUrl}</a>
            : prUrl || 'none yet'}
        </dd>
      </div>
    </dl>
  );
}

function TaskItem({ task, onCancel, busy, error }: {
  task: Rec; onCancel: (id: string) => void; busy: boolean; error: string;
}) {
  const id = asText(task.task_id);
  const status = asText(task.status);
  const proposal = asRec(task.proposal);
  const reason = asText(task.reason);
  return (
    <li className="gagos-tasks__item">
      <div className="gagos-tasks__head">
        <code>{id}</code>
        <span className={`gagos-tasks__status gagos-tasks__status--${status}`}>Status: {status || 'unknown'}</span>
      </div>
      <p>File <code>{asText(task.rel)}</code></p>
      <TaskText text={asText(task.text)} />
      {reason && <p>{reason}</p>}
      {proposal && <Progress proposal={proposal} />}
      {status === 'open' && (
        <button type="button" disabled={busy} onClick={() => onCancel(id)}>Cancel this task</button>
      )}
      {error && <p role="alert" className="gagos-tasks__error">{error}</p>}
    </li>
  );
}

export default function GagosTasksPanel() {
  const tasks = useResource('/api/gagos/tasks', parseTasks, noRecords);
  const [file, setFile] = useState('');
  const [text, setText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [cancelling, setCancelling] = useState('');
  const [cancelErrors, setCancelErrors] = useState<Record<string, string>>({});
  const { refresh } = tasks;

  // A gentle poll, only while the panel is mounted.
  useEffect(() => {
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const ready = file.trim() !== '' && text.trim() !== '' && text.length <= MAX_TASK_CHARS && !submitting;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    setSubmitting(true); setFormError('');
    try {
      const result = await sendGuardedCommand('/api/gagos/tasks', { file: file.trim(), text });
      if (result.status === 'accepted') { setText(''); } else { setFormError(rejectionText(result)); }
    } finally { setSubmitting(false); refresh(); }
  }

  async function cancel(id: string) {
    setCancelling(id);
    setCancelErrors((old) => ({ ...old, [id]: '' }));
    try {
      const result = await sendGuardedCommand(`/api/gagos/tasks/${encodeURIComponent(id)}/cancel`, {});
      if (result.status !== 'accepted') setCancelErrors((old) => ({ ...old, [id]: rejectionText(result) }));
    } finally { setCancelling(''); refresh(); }
  }

  return (
    <section className="gagos-panel gagos-tasks" aria-label="GAGOS tasks">
      <h3>GAGOS tasks</h3>
      <p>
        Say what to change in one file. GAGOS&apos;s writers make it, the sandbox runs its tests,
        Claude Code reviews it, and GAGOS opens the pull request for you to merge.
      </p>
      <form className="gagos-tasks__form" onSubmit={(e) => void submit(e)}>
        <label htmlFor="gagos-task-file">File (relative to the project)</label>
        <input id="gagos-task-file" type="text" value={file} autoComplete="off" spellCheck={false}
          placeholder="aios/example.py" onChange={(e) => setFile(e.target.value)} />
        <label htmlFor="gagos-task-text">What should change</label>
        <textarea id="gagos-task-text" value={text} rows={5}
          onChange={(e) => setText(e.target.value)} />
        <p className={text.length > MAX_TASK_CHARS ? 'gagos-tasks__count gagos-tasks__error' : 'gagos-tasks__count'}
          aria-live="polite">{text.length} / {MAX_TASK_CHARS} characters</p>
        <button type="submit" disabled={!ready}>Give GAGOS this task</button>
        {submitting && <p role="status">Sending…</p>}
        {formError && <p role="alert" className="gagos-tasks__error">{formError}</p>}
      </form>
      <h4>Tasks</h4>
      <ResourceNotice resource={tasks} empty="No tasks have been written yet." />
      <ul className="gagos-tasks__list">
        {tasks.data?.map((task) => (
          <TaskItem key={asText(task.task_id)} task={task} onCancel={(id) => void cancel(id)}
            busy={cancelling === asText(task.task_id)} error={cancelErrors[asText(task.task_id)] ?? ''} />
        ))}
      </ul>
    </section>
  );
}
