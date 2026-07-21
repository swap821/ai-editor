import { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Minus, X, Maximize2 } from 'lucide-react';

export default function HUDPanel({
  _id,
  title = 'Panel',
  tint = 'base', // base, cyan, purple, amber, green
  defaultPosition = { x: 50, y: 50 },
  defaultSize = { width: 400, height: 500 },
  onClose,
  children,
  headerExtras,
}) {
  const [isMinimized, setIsMinimized] = useState(false);
  const [size, setSize] = useState(defaultSize);
  const panelRef = useRef(null);

  // Tint mapping for borders and glows
  const tintStyles = {
    base: {
      border: 'var(--border)',
      glow: 'none',
      bg: 'var(--ag-surface-base)',
      headerBg: 'rgba(10, 11, 16, 0.8)',
    },
    cyan: {
      border: '1px solid rgba(123, 245, 251, 0.2)',
      glow: 'var(--ag-glow-cyan)',
      bg: 'var(--ag-surface-cyan)',
      headerBg: 'rgba(10, 14, 18, 0.8)',
    },
    purple: {
      border: '1px solid rgba(167, 139, 250, 0.2)',
      glow: 'var(--ag-glow-purple)',
      bg: 'var(--ag-surface-purple)',
      headerBg: 'rgba(14, 10, 18, 0.8)',
    },
    amber: {
      border: '1px solid rgba(251, 191, 36, 0.2)',
      glow: 'var(--ag-glow-amber)',
      bg: 'var(--ag-surface-amber)',
      headerBg: 'rgba(18, 14, 10, 0.8)',
    },
    green: {
      border: '1px solid rgba(52, 211, 153, 0.2)',
      glow: 'inset 0 0 20px rgba(52, 211, 153, 0.06)',
      bg: 'rgba(10, 18, 14, 0.85)',
      headerBg: 'rgba(10, 18, 14, 0.8)',
    },
  };

  const currentTint = tintStyles[tint] || tintStyles.base;

  const handleResize = (e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startY = e.clientY;
    const startWidth = size.width;
    const startHeight = size.height;

    const onMouseMove = (moveEvent) => {
      setSize({
        width: Math.max(200, startWidth + (moveEvent.clientX - startX)),
        height: Math.max(100, startHeight + (moveEvent.clientY - startY)),
      });
    };

    const onMouseUp = () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  };

  return (
    <AnimatePresence>
      <motion.div
        ref={panelRef}
        drag
        dragHandle=".drag-handle"
        dragMomentum={false}
        initial={{ opacity: 0, y: 20, scale: 0.96, filter: 'blur(8px)' }}
        animate={{
          opacity: 1,
          y: 0,
          scale: 1,
          filter: 'blur(0px)',
          transition: {
            duration: 0.6,
            ease: [0.34, 1.56, 0.64, 1], // ag-spring
          },
        }}
        exit={{ opacity: 0, scale: 0.96, filter: 'blur(8px)', transition: { duration: 0.2 } }}
        style={{
          position: 'absolute',
          top: defaultPosition.y,
          left: defaultPosition.x,
          width: isMinimized ? 200 : size.width,
          height: isMinimized ? 40 : size.height,
          backgroundColor: isMinimized ? currentTint.headerBg : currentTint.bg,
          border: currentTint.border,
          boxShadow: currentTint.glow,
          borderRadius: 'var(--radius-md)',
          backdropFilter: isMinimized ? 'none' : 'var(--ag-blur-lg) var(--ag-saturate)',
          WebkitBackdropFilter: isMinimized ? 'none' : 'var(--ag-blur-lg) var(--ag-saturate)',
          willChange: 'transform',
          transform: 'translateZ(0)',
          contain: 'layout style paint',
          pointerEvents: 'auto',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          zIndex: 10,
        }}
      >
        {/* Header (Drag Handle) */}
        <div
          className="drag-handle"
          style={{
            height: 40,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 12px',
            backgroundColor: currentTint.headerBg,
            borderBottom: isMinimized ? 'none' : 'var(--hairline)',
            cursor: 'grab',
            userSelect: 'none',
          }}
          whileTap={{ cursor: 'grabbing' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--text-1)' }}>
              {title}
            </span>
            {headerExtras}
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setIsMinimized(!isMinimized)}
              style={{ background: 'transparent', border: 'none', color: 'var(--text-2)', padding: '4px' }}
              aria-label={isMinimized ? "Maximize" : "Minimize"}
            >
              {isMinimized ? <Maximize2 size={14} /> : <Minus size={14} />}
            </button>
            {onClose && (
              <button
                onClick={onClose}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-2)', padding: '4px' }}
                aria-label="Close"
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        {!isMinimized && (
          <div style={{ flex: 1, overflow: 'auto', position: 'relative' }}>
            {children}
          </div>
        )}

        {/* Resize Handle */}
        {!isMinimized && (
          <div
            onMouseDown={handleResize}
            style={{
              position: 'absolute',
              bottom: 0,
              right: 0,
              width: 15,
              height: 15,
              cursor: 'nwse-resize',
              zIndex: 20,
            }}
          />
        )}
      </motion.div>
    </AnimatePresence>
  );
}
