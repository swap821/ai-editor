import * as THREE from 'three';
import type { MaterializedTabKind } from './tabStore';
export {
  BRAINSTEM_INTAKE_LOCAL, DEFAULT_VERTEBRA_SEAT_INDEX, VERTEBRA_SEAT_ORDER,
  getInputSurfacePlacement, getContentSurfacePlacement, getApprovalSurfacePlacement,
  selectNextAvailableVertebraSeat, type MaterializedSurfacePlacement,
} from './surfacePlacement';

export const FOCUSED_HUD_NERVE_GAP = 0.022;
const FOCUSED_HUD_NERVE_APPROACH = 0.14;

export function shouldUseFocusedHudUmbilical(kind: MaterializedTabKind, focused: boolean): boolean {
  return kind === 'content' && focused;
}

export function buildFocusedHudUmbilicalCurve(
  origin: THREE.Vector3,
  panelRim: THREE.Vector3,
  panelUp: THREE.Vector3,
): THREE.CatmullRomCurve3 {
  const up = panelUp.clone().normalize();
  const endpoint = panelRim.clone().addScaledVector(up, -FOCUSED_HUD_NERVE_GAP);
  const approach = endpoint.clone().addScaledVector(up, -FOCUSED_HUD_NERVE_APPROACH);
  const mid = origin.clone().lerp(approach, 0.68);
  return new THREE.CatmullRomCurve3([origin.clone(), mid, approach, endpoint]);
}
