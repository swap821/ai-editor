import type { MaterializedTabKind } from './tabStore';
import { deriveLivingWorkspacePose } from './livingWorkspaceLayout';

export interface MaterializedSurfacePoseInput {
  kind: MaterializedTabKind;
  focused: boolean;
  targetLocal: [number, number, number];
  waitingIndex?: number;
  viewportWidth?: number;
  viewportHeight?: number;
}

export interface MaterializedSurfacePose {
  targetLocal: [number, number, number];
  scale: number;
  opacity: number;
  tubeOpacity: number;
}

export function deriveMaterializedSurfacePose(input: MaterializedSurfacePoseInput): MaterializedSurfacePose {
  return deriveLivingWorkspacePose(input);
}
