import { STARTER_PATHS } from './starterPathData';

type StarterPathsProps = {
  onChoose: (prompt: string) => void;
};

export function StarterPaths({ onChoose }: StarterPathsProps) {
  return (
    <div className="gagos-starters gagos-starters--paths" role="group" aria-label="Choose how to begin">
      {STARTER_PATHS.map((path) => (
        <button
          key={path.id}
          type="button"
          className={`gagos-starter gagos-starter--path${path.id === 'understand' ? ' gagos-starter--featured' : ''}`}
          aria-label={`${path.title}. ${path.description} Select to fill a starter prompt; it will not be sent automatically.`}
          onClick={() => onChoose(path.prompt)}
        >
          <span className="gagos-starter__title">{path.title}</span>
          <span className="gagos-starter__description">{path.description}</span>
          <span className="gagos-starter__action">Use this path</span>
        </button>
      ))}
    </div>
  );
}
