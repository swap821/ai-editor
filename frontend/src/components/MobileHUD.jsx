/**
 * MobileHUD wraps the main Superbrain chrome on smaller screens
 * to provide a simplified, touch-friendly UI.
 */
export default function MobileHUD({ children }) {
  const isMobile = window.innerWidth <= 768;

  if (!isMobile) return children;

  return (
    <div 
      className="mobile-hud" 
      style={{
        position: 'fixed',
        inset: 0,
        pointerEvents: 'none',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-end',
        padding: '16px',
        zIndex: 100
      }}
      data-testid="mobile-hud"
    >
      <div 
        style={{
          pointerEvents: 'auto',
          background: 'rgba(0, 0, 0, 0.6)',
          backdropFilter: 'blur(16px)',
          border: '1px solid var(--border)',
          borderRadius: '16px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px'
        }}
      >
        <div style={{ fontSize: '14px', fontWeight: 'bold', color: 'var(--foreground)', textAlign: 'center' }}>
          Mobile Operator Interface
        </div>
        <div style={{ color: 'var(--muted-foreground)', fontSize: '12px', textAlign: 'center' }}>
          Pinch to zoom, swipe to rotate brain.
        </div>
      </div>
      {/* Hide original desktop panels if necessary, or render them modified */}
      <div style={{ display: 'none' }}>
        {children}
      </div>
    </div>
  );
}
