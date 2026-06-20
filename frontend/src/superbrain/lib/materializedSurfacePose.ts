import type { MaterializedTabKind } from './tabStore';
import { deriveLivingWorkspacePose } from './livingWorkspaceLayout';

export interface MaterializedSurfacePoseInput {
  kind: MaterializedTabKind;
  focused: boolean;
  targetLocal: [number, number, number];
  waitingIndex?: number;
  viewportWidth?: number;
  viewportHeight?: number;
  /** points-being: place the born tab as a lateral peer beside the being (poster phase 4). */
  points?: boolean;
  /** active work-tab count — drives orchestration (2+) vs single-tab placement. */
  workCount?: number;
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
