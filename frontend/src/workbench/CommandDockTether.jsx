// CommandDockTether — the DOM↔3D bridge of the NeuralCommandDock. Draws a thin
// luminous nerve from the dock up into the being's living brainstem (whose screen
// position the 3D scene publishes via stemAnchorBus), and runs command-BEADS along
// it toward the stem while typing/sending — "my words travel into its nervous
// system." Contextual: faint at rest, brightens when engaged; beads only on flow.
// Pure-DOM SVG, rAF-driven (no per-frame React re-render). Sacred palette (cyan).

import { useEffect, useRef } from 'react';
import { getFunnelAnchor } from '../superbrain/lib/funnelAnchorBus';

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
      const funnel = getFunnelAnchor();
      const path = pathRef.current;
      const bar = document.querySelector('.gagos-bar');
      const sendBtn = document.querySelector('.gagos-send');
      if (path && bar && funnel.visible) {
        // ONE END anchors to the SEND (->) BUTTON itself — the synapse where the
        // operator's words FIRE into the nerve (operator call). Falls back to the bar.
        const r = (sendBtn || bar).getBoundingClientRect();
        const x0 = r.left + r.width * 0.5; // the -> button's centre
        const y0 = r.top + r.height * 0.5;
        const x1 = funnel.x;
        // nudge the tip UP into the spine so the nerve TOUCHES / merges with the
        // convergence (no gap) — the chat's nerve plugging INTO the cord, since the
        // command dock is its own small organ of the being (operator call).
        const y1 = funnel.y - 12;
        // a gentle nerve reaching ACROSS into the being's intake-funnel mouth — the
        // funnel sits low (near the dock), so a soft dip, not a high arc to the stem.
        // approach the convergence (conus) VERTICALLY from below — control point
        // directly under it — so the nerve sweeps from the -> button through the rings
        // CENTRE and rises straight up into the neck, matching the operator's sketch.
        const mx = x1;
        const my = y1 + 64;
        path.setAttribute('d', `M ${x0} ${y0} Q ${mx} ${my} ${x1} ${y1}`);
        // a PRESENT nerve (not near-invisible) — the operator's command channel: calm
        // at rest, brighter when engaged.
        path.setAttribute('opacity', (p.active ? 0.5 + p.intensity * 0.3 : 0.28).toFixed(3));
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
      <defs>
        {/* the SEND (->) BUTTON's exact purple gradient (#b06eff -> #6a1eff), so the
            intake nerve reads as the operator's own command channel (operator call). */}
        <linearGradient id="gagos-nerve-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#b06eff" />
          <stop offset="100%" stopColor="#6a1eff" />
        </linearGradient>
      </defs>
      <path
        ref={pathRef}
        fill="none"
        stroke="url(#gagos-nerve-grad)"
        strokeWidth="2.2"
        strokeLinecap="round"
        opacity="0"
        style={{ filter: 'drop-shadow(0 0 6px rgba(176, 110, 255, 0.7))' }}
      />
      {Array.from({ length: BEADS }).map((_, i) => (
        <circle
          key={i}
          ref={(el) => {
            beadRefs.current[i] = el;
          }}
          r="2.6"
          fill="#dcc6ff"
          opacity="0"
          style={{ filter: 'drop-shadow(0 0 6px rgba(176, 110, 255, 0.9))' }}
        />
      ))}
    </svg>
  );
}
