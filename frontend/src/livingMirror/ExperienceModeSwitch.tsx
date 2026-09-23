import type { ExperienceMode } from './experienceMode';

type ExperienceModeSwitchProps = {
  mode: ExperienceMode;
  onChange: (mode: ExperienceMode) => void;
};

export function ExperienceModeSwitch({ mode, onChange }: ExperienceModeSwitchProps) {
  return (
    <div className="gagos-experience-mode" role="group" aria-label="Experience mode">
      <span className="gagos-experience-mode__label">How you work</span>
      <div className="gagos-experience-mode__choices">
        <button
          type="button"
          className={`gagos-experience-mode__choice${mode === 'beginner' ? ' is-active' : ''}`}
          aria-pressed={mode === 'beginner'}
          onClick={() => onChange('beginner')}
        >
          Guided
        </button>
        <button
          type="button"
          className={`gagos-experience-mode__choice${mode === 'expert' ? ' is-active' : ''}`}
          aria-pressed={mode === 'expert'}
          onClick={() => onChange('expert')}
        >
          Expert / Mirror
        </button>
      </div>
      <span className="gagos-experience-mode__state" aria-live="polite">
        {mode === 'beginner' ? 'Guided front door' : 'Full operational mirror'}
      </span>
    </div>
  );
}
