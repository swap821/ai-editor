import { useEffect, useRef } from 'react';

/* ──────────────────────────────────────────────────────────────────────────
   AmbientVoid — a cheap, dependency-free WebGL field behind the workspace.

   A near-black "void" with a slow violet/blue undulation that intensifies when
   the AI is working (`energy` 0→1). Deliberately lightweight so it can run
   alongside local inference on a modest machine:
     • raw WebGL (no three.js), one fullscreen triangle, a 2-sample noise shader
     • internal resolution capped at 0.6× and throttled to ~30fps
     • paused when the tab is hidden; static single frame under reduced-motion
     • purely decorative: position:fixed, z-index:-1, pointer-events:none
   If WebGL is unavailable or a shader fails to compile, it silently no-ops
   (the app just falls back to the solid canvas colour behind it).
   ────────────────────────────────────────────────────────────────────────── */

const VERT = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAG = `
precision mediump float;
uniform vec2  uRes;
uniform float uTime;
uniform float uEnergy;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes.xy;
  vec2 p  = uv * 2.0 - 1.0;
  p.x *= uRes.x / uRes.y;

  float t = uTime * (0.02 + uEnergy * 0.06);
  float n = noise(p * 1.5 + vec2(t, t * 0.7));
  n += 0.5 * noise(p * 3.0 - vec2(t * 0.8, t));
  n /= 1.5;

  vec3 col    = vec3(0.018, 0.022, 0.038);          // near-black base
  vec3 violet = vec3(0.34, 0.12, 0.55);             // rim light 1
  vec3 blue   = vec3(0.10, 0.30, 0.70);             // rim light 2
  float glow  = smoothstep(0.30, 0.92, n);
  col += violet * glow        * (0.045 + uEnergy * 0.11);
  col += blue   * (1.0 - glow) * (0.030 + uEnergy * 0.08);

  float vig = smoothstep(1.5, 0.15, length(p));     // gentle centre lift
  col *= 0.55 + 0.45 * vig;

  gl_FragColor = vec4(col, 1.0);
}
`;

export default function AmbientVoid({ energy = 0 }) {
  const canvasRef = useRef(null);
  const targetRef = useRef(energy);
  const easedRef = useRef(energy);

  // Let the parent nudge energy (e.g. isStreaming) without restarting the loop.
  useEffect(() => { targetRef.current = energy; }, [energy]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext('webgl', { antialias: false, alpha: false, depth: false, powerPreference: 'low-power' });
    if (!gl) return;

    const compile = (type, src) => {
      const sh = gl.createShader(type);
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      return gl.getShaderParameter(sh, gl.COMPILE_STATUS) ? sh : null;
    };
    const vs = compile(gl.VERTEX_SHADER, VERT);
    const fs = compile(gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return;

    const prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const aPos = gl.getAttribLocation(prog, 'aPos');
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    const uRes = gl.getUniformLocation(prog, 'uRes');
    const uTime = gl.getUniformLocation(prog, 'uTime');
    const uEnergy = gl.getUniformLocation(prog, 'uEnergy');

    const SCALE = 0.6;
    const resize = () => {
      const w = Math.max(1, Math.floor(window.innerWidth * SCALE));
      const h = Math.max(1, Math.floor(window.innerHeight * SCALE));
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
    };
    resize();
    window.addEventListener('resize', resize);

    const draw = (timeSec) => {
      easedRef.current += (targetRef.current - easedRef.current) * 0.05;
      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform1f(uTime, timeSec);
      gl.uniform1f(uEnergy, easedRef.current);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
      draw(0); // one static frame, no loop
      return () => {
        window.removeEventListener('resize', resize);
        gl.getExtension('WEBGL_lose_context')?.loseContext();
      };
    }

    let raf = 0;
    let running = true;
    let last = 0;
    const start = performance.now();
    const FRAME_MS = 1000 / 30;

    const loop = (now) => {
      if (!running) return;
      raf = requestAnimationFrame(loop);
      if (now - last < FRAME_MS) return;
      last = now;
      draw((now - start) / 1000);
    };
    raf = requestAnimationFrame(loop);

    const onVis = () => {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else if (!running) {
        running = true;
        last = 0;
        raf = requestAnimationFrame(loop);
      }
    };
    document.addEventListener('visibilitychange', onVis);

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVis);
      gl.getExtension('WEBGL_lose_context')?.loseContext();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      style={{
        position: 'fixed',
        inset: 0,
        width: '100%',
        height: '100%',
        zIndex: -1,
        pointerEvents: 'none',
        display: 'block',
      }}
    />
  );
}
