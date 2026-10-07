import { useEffect, useState } from 'react';
import { subscribePendingApproval } from '../../superbrain/lib/aiosAdapter';
import { subscribeCognition } from '../../superbrain/lib/cognitionBus';
import {
  getActiveBrain,
  setActiveBrain,
  subscribeActiveBrain,
} from '../../superbrain/lib/activeBrain';
import {
  getConversationPhase,
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

function findVerificationArtifact(rawTarget) {
  const target = String(rawTarget ?? '').replace(/\\/g, '/');
  const targetBase = target.split('/').pop();
  const snap = getTabStoreSnapshot();
  const candidates = [...new Map([...snap.tabs, ...(snap.recoverableTabs ?? [])]
    .filter((tab) => tab.kind === 'content' && tab.content)
    .map((tab) => [tab.id, tab])).values()];
  const exact = candidates.filter((tab) => tab.content.filepath?.replace(/\\/g, '/') === target);
  const byName = candidates.filter((tab) => tab.content.filepath?.split(/[\\/]/).pop() === targetBase);
  // A backend prefix can qualify a basename-only artifact. It cannot
  // erase a different path already known for that artifact, and basename
  // fallback must still be unique across active and retained results.
  const basenameCompatible = byName.length === 1 && (!target.includes('/')
    || !byName[0].content.filepath.replace(/\\/g, '/').includes('/'));
  const matches = exact.length > 0 ? exact : basenameCompatible ? byName : [];
  // Never attach an explicitly targeted or ambiguous check to another
  // focused reader. A filename is usable only when it identifies one
  // retained version. The toast can still report the received event.
  return target ? (matches.length === 1 ? matches[0] : null)
    : candidates.length === 1 && candidates[0].id === snap.focusId ? candidates[0] : null;
}

export function useCognitionBus(reducedMotion = false) {
  const [brainChip, setBrainChip] = useState(() => formatActiveBrainChip(getActiveBrain()));
  const [pendingApproval, setPendingApproval] = useState(null);
  const [convPhase, setConvPhase] = useState(() => getConversationPhase());
  const [verifyToast, setVerifyToast] = useState(null);
  const [reflexActive, setReflexActive] = useState(false);

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

  // A real cerebellum replay is not model thinking. This is a measured
  // cognition event and never authorizes the replayed action.
  useEffect(() => {
    return subscribeCognition((event) => {
      if (event.type === 'reflex-recall') {
        setReflexActive(true);
        return;
      }
      if (['directive', 'route', 'verify', 'error', 'approval-required', 'approval-resolved'].includes(event.type)) {
        setReflexActive(false);
      }
    });
  }, []);

  // Verify toast notifications & tab output enrichment
  useEffect(() => {
    return subscribeCognition((event) => {
      if (event.type === 'verify' && event.data?.verdict) {
        const toastToken = {};
        const reportedVerdict = String(event.data.verdict).toLowerCase();
        const verdict = ['pass', 'passed', 'green'].includes(reportedVerdict) ? 'pass'
          : ['fail', 'failed', 'red'].includes(reportedVerdict) ? 'fail' : 'unknown';
        const output = String(event.data.output ?? '');
        const match = findVerificationArtifact(event.data.target);

        const attributed = Boolean(match?.content) && verdict !== 'unknown';
        setVerifyToast({
          verdict: attributed ? verdict : 'unknown',
          detail: event.detail || '',
          leaving: false,
          token: toastToken,
        });

        if (attributed) {
          const cursor = event.metadata?.mirrorEventId;
          const verifyEventId = event.source === 'mirror' && Number.isSafeInteger(cursor) && cursor >= 0
            ? cursor : undefined;
          updateMaterializedTab(match.id, {
            content: { ...match.content, verifyVerdict: verdict, verifyOutput: output, verifyEventId },
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
    reflexActive,
    setVerifyToast,
    setConvPhase,
    setPendingApproval,
  };
}
