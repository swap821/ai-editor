import { useMemo, useSyncExternalStore } from 'react';
import { useMirrorStore } from '../../superbrain/lib/mirrorStore';
import { useTabStore } from '../../superbrain/lib/tabStore';
import {
  getConversationPhase,
  subscribeConversationPhase,
  type ConversationPhase,
} from '../../superbrain/lib/conversationPhaseBus';
import { beingPresentationFromStores } from './presentationFromStores';
import { useEmergencyStopPresentation } from '../emergencyStopPresentation';
import { applyEmergencyStopPresentation } from './emergencyStopOverlay';

export function useBeingPresentation() {
  const mirror = useMirrorStore();
  const tabs = useTabStore();
  // Conversation phases are module-level because the R3F scene reads them in
  // frame loops. Subscribe here only to make DOM semantics update on events.
  const conversationPhase = useSyncExternalStore(
    subscribeConversationPhase,
    getConversationPhase,
    () => 'idle' as ConversationPhase,
  );
  const emergencyStop = useEmergencyStopPresentation();
  return useMemo(
    () => applyEmergencyStopPresentation(
      beingPresentationFromStores(mirror, tabs, conversationPhase),
      emergencyStop,
    ),
    [conversationPhase, emergencyStop, mirror, tabs],
  );
}
