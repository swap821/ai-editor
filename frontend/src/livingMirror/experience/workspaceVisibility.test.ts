import { describe, expect, it } from 'vitest';
import { isWorkspacePanelVisible, type WorkspaceVisibilityPanel } from './workspaceVisibility';

const panel = (kind: string): WorkspaceVisibilityPanel => ({ kind });

describe('workspace visibility by experience mode', () => {
  it('keeps Guided to human-facing workspaces', () => {
    expect(isWorkspacePanelVisible(panel('missions'), 'beginner')).toBe(true);
    expect(isWorkspacePanelVisible(panel('files'), 'beginner')).toBe(true);
    expect(isWorkspacePanelVisible(panel('file'), 'beginner')).toBe(true);
    expect(isWorkspacePanelVisible(panel('history'), 'beginner')).toBe(true);
    expect(isWorkspacePanelVisible(panel('terminal'), 'beginner')).toBe(false);
    expect(isWorkspacePanelVisible(panel('deliberation'), 'beginner')).toBe(false);
    expect(isWorkspacePanelVisible(panel('governance'), 'beginner')).toBe(false);
  });

  it('keeps every admitted workspace visible in Expert mode', () => {
    expect(isWorkspacePanelVisible(panel('terminal'), 'expert')).toBe(true);
    expect(isWorkspacePanelVisible(panel('deliberation'), 'expert')).toBe(true);
    expect(isWorkspacePanelVisible(panel('governance'), 'expert')).toBe(true);
  });
});
