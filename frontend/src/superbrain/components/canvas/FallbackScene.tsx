import './FallbackScene.css';

interface FallbackSceneProps {
  posture?: 'idle' | 'thinking' | 'speaking' | 'listening';
}

export function FallbackScene({ posture = 'idle' }: FallbackSceneProps) {
  return (
    <div className={`fallback-scene fallback-scene--${posture}`} aria-label="GAGOS presence (2D mode)">
      <div className="fallback-scene__orb" />
    </div>
  );
}
