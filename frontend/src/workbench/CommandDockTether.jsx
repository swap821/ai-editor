// CommandDockTether — the DOM↔3D bridge of the NeuralCommandDock. Draws a thin
// luminous nerve from the dock up into the being's living brainstem (whose screen
// position the 3D scene publishes via stemAnchorBus), and runs command-BEADS along
// it toward the stem while typing/sending — "my words travel into its nervous
// system." Contextual: faint at rest, brightens when engaged; beads only on flow.
// Pure-DOM SVG, rAF-driven (no per-frame React re-render). Sacred palette (cyan).

import { useEffect, useRef } from 'react';
import { getStemAnchor } from '../superbrain/lib/stemAnchorBus';

const BEADS = 4;

export default function CommandDockTether({ active, intensity, particleFlow, reducedMotion }) {
  const pathRef = useRef(null);
  const beadRefs = useRef([]);
  const propsRef = useRef({ active, intensity, particleFlow, reducedMotion });
  propsRef.current = { active, intensity, particleFlow, reducedMotion };

  useEffect(() => {
    let raf = 0;
    let t = 0;
    let last = performance.now();
    const tick = (now) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const p = propsRef.current;
      const stem = getStemAnchor();
      const path = pathRef.current;
      const bar = document.querySelector('.gagos-bar');
      if (path && bar && stem.visible) {
        const r = bar.getBoundingClientRect();
        const x0 = r.left + r.width * 0.5; // dock top-centre
        const y0 = r.top;
        const x1 = stem.x;
        const y1 = stem.y;
        // a gently bowed nerve rising from the dock toward the stem
        const mx = (x0 + x1) / 2;
        const my = (y0 + y1) / 2 - Math.abs(x1 - x0) * 0.14 - 40;
        path.setAttribute('d', `M ${x0} ${y0} Q ${mx} ${my} ${x1} ${y1}`);
        path.setAttribute('opacity', (p.active ? 0.22 + p.intensity * 0.34 : 0.05).toFixed(3));
        // beads travel dock → stem while there is command flow
        const flow = p.reducedMotion ? 0 : p.particleFlow;
        if (flow > 0) {
          t += dt * (0.5 + flow * 1.4);
          const len = path.getTotalLength();
          beadRefs.current.forEach((b, i) => {
            if (!b) return;
            const u = (t + i / BEADS) % 1; // 0 at dock → 1 at stem
            const pt = path.getPointAtLength(len * u);
            b.setAttribute('cx', pt.x.toFixed(1));
            b.setAttribute('cy', pt.y.toFixed(1));
            // fade in near the dock, out near the stem (arriving into the being)
            b.setAttribute('opacity', (flow * Math.sin(u * Math.PI) * 0.95).toFixed(3));
          });
        } else {
          beadRefs.current.forEach((b) => b && b.setAttribute('opacity', '0'));
        }
      } else if (path) {
        path.setAttribute('opacity', '0');
        beadRefs.current.forEach((b) => b && b.setAttribute('opacity', '0'));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <svg className="gagos-tether" aria-hidden="true">
      <path
        ref={pathRef}
        fill="none"
        stroke="#7bf5fb"
        strokeWidth="1.4"
        strokeLinecap="round"
        opacity="0"
        style={{ filter: 'drop-shadow(0 0 4px rgba(123, 245, 251, 0.6))' }}
      />
      {Array.from({ length: BEADS }).map((_, i) => (
        <circle
          key={i}
          ref={(el) => {
            beadRefs.current[i] = el;
          }}
          r="2.3"
          fill="#aef6ff"
          opacity="0"
          style={{ filter: 'drop-shadow(0 0 5px rgba(123, 245, 251, 0.85))' }}
        />
      ))}
    </svg>
  );
}
