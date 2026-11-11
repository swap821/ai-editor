import './initializeVisualText';
import BootSequence from '@/components/ui/BootSequence';
import WorkspaceCanvas from '@/components/canvas/WorkspaceCanvas';
import { SCENE_UNIFORMS } from '@/components/canvas/SuperbrainScene.LEGACY';
import SuperbrainReactiveEffects from './SuperbrainReactiveEffects';
import { WorkspaceConnectionProjection } from '../livingMirror/being/WorkspaceConnectionProjection';
import { WorkspaceThumbnailTargets } from '../livingMirror/being/WorkspaceThumbnailTargets';

/** Optional renderer evaluation lives below the operational DOM boundary. */
export default function OrganismScene({ booted, onBootComplete, physical, being, snapshot,
  inputAttentionActive, attentionTargetRef, workspaceConnectionRef }) {
  return <>
    {!booted && <BootSequence onComplete={onBootComplete} />}
    <WorkspaceCanvas booted={booted} physical={physical} inputAttentionActive={inputAttentionActive} attentionTargetRef={attentionTargetRef}>
      <SuperbrainReactiveEffects presentationOverride={being} physicalOverride={physical} inputAttentionActive={inputAttentionActive} />
      <WorkspaceConnectionProjection overlayRef={workspaceConnectionRef} snapshot={snapshot} attentionTargetRef={attentionTargetRef}
        motionHeld={physical?.conductor?.travel === 'frozen'} breathRef={SCENE_UNIFORMS.uBreath} />
      <WorkspaceThumbnailTargets overlayRef={workspaceConnectionRef} snapshot={snapshot} />
    </WorkspaceCanvas>
  </>;
}
