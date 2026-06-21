// frontend/src/superbrain/lib/curlNoiseTSL.ts
//
// Divergence-free curl-noise as a TSL Fn — inlines into the WebGPU compute graph
// (and compiles to GLSL on the WebGL2 fallback). Curl of a 3-channel noise
// "potential" field gives a swirling flow that never clumps (∇·curl = 0), which is
// what makes the point-field churn like living tissue instead of collapsing.
//
// Part of the flagged "Million-Mote Mind" spike — see gpuMode.ts. Unverified on a
// real WebGPU device (no headless GPU); the math mirrors the standard analytic curl.
import { Fn, vec3, float, mx_noise_float } from 'three/tsl';

/** vec3 potential = three decorrelated noise samples of the same point. */
const potential = Fn(([q]) =>
  vec3(mx_noise_float(q), mx_noise_float(q.add(31.4)), mx_noise_float(q.sub(57.7))),
);

/** curl(potential(p)) via central finite differences. Returns a vec3 flow vector. */
export const curlNoise3 = Fn(([p]) => {
  const e = float(0.1);
  const dx = vec3(e, 0, 0);
  const dy = vec3(0, e, 0);
  const dz = vec3(0, 0, e);

  const dpdx = potential(p.add(dx)).sub(potential(p.sub(dx)));
  const dpdy = potential(p.add(dy)).sub(potential(p.sub(dy)));
  const dpdz = potential(p.add(dz)).sub(potential(p.sub(dz)));

  // curl = (∂Pz/∂y − ∂Py/∂z, ∂Px/∂z − ∂Pz/∂x, ∂Py/∂x − ∂Px/∂y)
  return vec3(
    dpdy.z.sub(dpdz.y),
    dpdz.x.sub(dpdx.z),
    dpdx.y.sub(dpdy.x),
  ).div(e.mul(2.0));
});
