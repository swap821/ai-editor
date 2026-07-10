import * as THREE from 'three';
import type { OrganMaterialState } from '@/lib/organMaterialState';

/**
 * Shared color/material tokens derived once per tab from its OrganMaterialState.
 * Extracted from MaterializedTab.tsx (structure audit, 2026-07-10) so the
 * skin components living alongside it can share this type without a
 * circular import back into the main file.
 */
export type SurfaceTheme = {
  reach: THREE.Color;
  live: THREE.Color;
  frame: THREE.Color;
  body: string;
  header: string;
  accent: string;
  outline: string;
  plate: string;
  text: string;
  muted: string;
  point: string;
};

export function toSurfaceTheme(material: OrganMaterialState): SurfaceTheme {
  return {
    reach: new THREE.Color(material.palette.reach),
    live: new THREE.Color(material.palette.live),
    frame: new THREE.Color(material.palette.frame),
    body: material.palette.body,
    header: material.palette.header,
    accent: material.palette.accent,
    outline: material.palette.outline,
    plate: material.palette.plate,
    text: material.palette.text,
    muted: material.palette.muted,
    point: material.palette.point,
  };
}
