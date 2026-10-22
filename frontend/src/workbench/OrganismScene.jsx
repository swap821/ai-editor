import './initializeVisualText';
import BootSequence from '@/components/ui/BootSequence';
import WorkspaceCanvas from '@/components/canvas/WorkspaceCanvas';
import SuperbrainReactiveEffects from './SuperbrainReactiveEffects';
import { WorkspaceConnectionProjection } from '../livingMirror/being/WorkspaceConnectionProjection';

/** Optional renderer evaluation lives below the operational DOM boundary. */
export default function OrganismScene({ booted, onBootComplete, physical, being, snapshot,
  inputAttentionActive, attentionTargetRef, workspaceConnectionRef }) {
  return <>
    {!booted && <BootSequence onComplete={onBootComplete} />}
    <WorkspaceCanvas booted={booted} physical={physical} inputAttentionActive={inputAttentionActive} attentionTargetRef={attentionTargetRef}>
      <SuperbrainReactiveEffects presentationOverride={being} physicalOverride={physical} inputAttentionActive={inputAttentionActive} />
      <WorkspaceConnectionProjection overlayRef={workspaceConnectionRef} snapshot={snapshot} attentionTargetRef={attentionTargetRef} />
    </WorkspaceCanvas>
  </>;
}
