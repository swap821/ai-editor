import { describeTaskState } from './copy';
import { taskStoryStepState, type HumanTaskState } from './humanTaskStory';

type GuidedTaskStoryProps = {
  state: HumanTaskState;
  goal?: string;
};

const steps = [
  ['asked', 'You asked'],
  ['understood', 'I understood'],
  ['preparing', 'I am preparing'],
  ['permission', 'Your permission'],
  ['working', 'I am working'],
  ['checking', 'I checked the result'],
  ['result', 'What happened'],
] as const;

export function GuidedTaskStory({ state, goal }: GuidedTaskStoryProps) {
  const copy = describeTaskState(state);
  return (
    <section className={`gagos-task-story gagos-task-story--${state}`} aria-labelledby="gagos-task-story-title" data-task-state={state}>
      <div className="gagos-task-story__heading">
        <div>
          <p className="gagos-task-story__eyebrow">Your task</p>
          <h2 id="gagos-task-story-title">{copy.title}</h2>
        </div>
        <span className="gagos-task-story__signal" aria-hidden="true" />
      </div>
      {goal ? <p className="gagos-task-story__goal">“{goal}”</p> : null}
      <p className="gagos-task-story__detail">{copy.detail}</p>
      <ol className="gagos-task-story__steps" aria-label="Task progress">
        {steps.map(([id, label]) => {
          const stepState = taskStoryStepState(state, id);
          return <li key={id} className={`gagos-task-story__step gagos-task-story__step--${stepState}`} aria-current={stepState === 'current' ? 'step' : undefined}>
            <span className="gagos-task-story__step-dot" aria-hidden="true" />
            <span>{label}</span>
          </li>;
        })}
      </ol>
      {copy.nextAction ? <p className="gagos-task-story__next"><strong>Next:</strong> {copy.nextAction}</p> : null}
    </section>
  );
}
