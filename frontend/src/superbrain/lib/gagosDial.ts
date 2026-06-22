/** Dev-only console dial for live FIDELITY tuning of the GAGOS in-world UI.
 *  Read off `window.__GAGOS` (e.g. window.__GAGOS = { x:-1.9, y:1.1, z:-4, horizon:0.1 }). */
export interface GagosDial {
  x?: number;
  y?: number;
  z?: number;
  horizon?: number;
}
