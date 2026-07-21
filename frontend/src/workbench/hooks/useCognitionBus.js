import { useEffect, useState } from 'react';
import { subscribePendingApproval } from '../../superbrain/lib/aiosAdapter';
import { publishCognition, subscribeCognition } from '../../superbrain/lib/cognitionBus';
import {
  getActiveBrain,
  setActiveBrain,
  subscribeActiveBrain,
} from '../../superbrain/lib/activeBrain';
import {
  getConversationPhase,
  setConversationPhase,
  subscribeConversationPhase,
} from '../../superbrain/lib/conversationPhaseBus';
import {
  getTabStoreSnapshot,
  updateMaterializedTab,
} from '../../superbrain/lib/tabStore';

export function formatActiveBrainChip(brain) {
  const model = String(brain?.model || '').trim();
  const provider = String(brain?.provider || '').trim();
  const privacy = String(brain?.privacy || '').trim().toLowerCase();
  const mode = String(brain?.mode || '').trim().toLowerCase();
  const name = model || provider || 'auto';
  const meta = [
    model && provider && provider.toLowerCase() !== model.toLowerCase() ? provider : '',
    privacy,
    mode,
  ].filter(Boolean).join(' · ');
  return { name, meta, mode };
}

export function useCognitionBus(reducedMotion = false) {
  const [brainChip, setBrainChip] = useState(() => formatActiveBrainChip(getActiveBrain()));
  const [pendingApproval, setPendingApproval] = useState(null);
  const [convPhase, setConvPhase] = useState(() => getConversationPhase());
  const [verifyToast, setVerifyToast] = useState(null);

  // Live active-LLM line from router `route` events
  useEffect(() => {
    return subscribeActiveBrain(() => {
      setBrainChip(formatActiveBrainChip(getActiveBrain()));
    });
  }, []);

  // Pending approval gate
  useEffect(() => {
    return subscribePendingApproval(setPendingApproval);
  }, []);

  // Live conversation phase bus + poll
  useEffect(() => {
    const sync = () => setConvPhase(getConversationPhase());
    const unsub = subscribeConversationPhase(sync);
    const id = window.setInterval(sync, 500);
    return () => {
      unsub();
      window.clearInterval(id);
    };
  }, []);

  // Route updates from cognition bus
  useEffect(() => {
    return subscribeCognition((event) => {
      if (event.type === 'route' && event.data) {
        setActiveBrain({
          provider: event.data.provider,
          model: event.data.model,
          privacy: event.data.privacy,
          turn_id: event.data.turn_id,
          mode: event.data.mode,
        });
      }
    });
  }, []);

  // Verify toast notifications & tab output enrichment
  useEffect(() => {
    return subscribeCognition((event) => {
      if (event.type === 'verify' && event.data?.verdict) {
        const toastToken = {};
        setVerifyToast({
          verdict: event.data.verdict,
          detail: event.detail || '',
          leaving: false,
          token: toastToken,
        });

        const verdict = String(event.data.verdict).toLowerCase() === 'pass' ? 'pass' : 'fail';
        const output = String(event.data.output ?? '');
        const targetBase = String(event.data.target ?? '').split(/[\\/]/).pop();
        const snap = getTabStoreSnapshot();
        const match =
          snap.tabs.find(
            (t) => t.kind === 'content' && t.content && t.content.filepath?.split(/[\\/]/).pop() === targetBase,
          ) || snap.tabs.find((t) => t.id === snap.focusId && t.kind === 'content');

        if (match && match.content) {
          updateMaterializedTab(match.id, {
            content: { ...match.content, verifyVerdict: verdict, verifyOutput: output },
          });
        }

        if (reducedMotion) {
          const id = window.setTimeout(() => {
            setVerifyToast((current) => (current?.token === toastToken ? null : current));
          }, 2600);
          return () => window.clearTimeout(id);
        }

        const timers = [];
        timers.push(
          window.setTimeout(() => {
            setVerifyToast((current) => (current?.token === toastToken ? { ...current, leaving: true } : current));
            timers.push(
              window.setTimeout(() => {
                setVerifyToast((current) => (current?.token === toastToken ? null : current));
              }, 250),
            );
          }, 2600),
        );
        return () => timers.forEach((t) => window.clearTimeout(t));
      }
    });
  }, [reducedMotion]);

  return {
    brainChip,
    pendingApproval,
    convPhase,
    verifyToast,
    setVerifyToast,
    setConvPhase,
    setPendingApproval,
  };
}
