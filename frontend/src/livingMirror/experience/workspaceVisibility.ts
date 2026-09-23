import type { ExperienceMode } from '../experienceMode';

export type WorkspaceVisibilityPanel = { kind: string };

const guidedPanelKinds = new Set(['missions', 'files', 'file', 'history']);

/** Presentation policy only: this never closes, authorizes, or mutates a panel. */
export function isWorkspacePanelVisible(panel: WorkspaceVisibilityPanel, mode: ExperienceMode): boolean {
  return mode === 'expert' || guidedPanelKinds.has(panel.kind);
}
