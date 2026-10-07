/** Preserve authored puncta at normal sizes; avoid fixed-pixel particles
 * swallowing the silhouette in a compact presence canvas. The 168px phone
 * body band is the reference. No point resampling, palette or DPR change. */
export function pointViewportScale(height: number): number {
  return Number.isFinite(height) && height > 0 ? Math.min(1, height / 168) : 1;
}

/** A widened stage is drawing coverage, not permission to enlarge puncta. */
export function pointPresenceHeight(camera: { view?: { enabled: boolean; fullHeight: number } | null }, stageHeight: number): number {
  return camera.view?.enabled ? camera.view.fullHeight : stageHeight;
}
