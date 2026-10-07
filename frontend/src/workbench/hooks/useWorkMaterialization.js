import { useCallback, useRef, useState } from 'react';
import {
  sendDirective,
  sendVoiceTurn,
  fetchOnboardingState,
  correctHumanState,
} from '../../superbrain/lib/aiosAdapter';
import { publishCognition } from '../../superbrain/lib/cognitionBus';
import { isWorkIntent } from '../../superbrain/lib/intentRouting';
import {
  setConversationPhase,
  getConversationPhase,
} from '../../superbrain/lib/conversationPhaseBus';
import {
  showContentSurface,
  getOccupiedVertebraSeats,
  beginRetractingMaterializedTab,
  claimWorkMaterialization,
  releaseWorkMaterialization,
  updateMaterializedTab,
  getTabStoreSnapshot,
  focusMaterializedTab,
  setWorkResultOutcome,
} from '../../superbrain/lib/tabStore';
import {
  getContentSurfacePlacement,
  selectNextAvailableVertebraSeat,
} from '../../superbrain/lib/materializedSurfaceAnchors';
import { sanitizeToText } from '../../utils/sanitizeHtml';
import { isCompleteWorkResult, isEstablishedTurn } from './turnOutcome';

const MAX_MESSAGES = 40;

const LANG_EXT = {
  python: 'py', py: 'py', javascript: 'js', js: 'js', jsx: 'jsx', typescript: 'ts',
  ts: 'ts', tsx: 'tsx', bash: 'sh', sh: 'sh', shell: 'sh', json: 'json',
  html: 'html', css: 'css', sql: 'sql', go: 'go', rust: 'rs', c: 'c', cpp: 'cpp', text: 'txt',
};

function stripAlignmentPreamble(answer) {
  return String(answer ?? '')
    .replace(
      /^(?:\s*(?:Unverified assumptions before proceeding:[^\n]*|Unresolved but treated as non-blocking:[^\n]*)\s*\n?)+/gi,
      '',
    )
    .replace(/^\s+/, '');
}

function extractWork(answer) {
  const raw = stripAlignmentPreamble(answer);
  const fence = raw.match(/```(\w+)?\s*\n([\s\S]*?)```/);
  if (fence) {
    return { code: fence[2].replace(/\s+$/, ''), language: (fence[1] || 'text').toLowerCase(), hasCode: true };
  }
  return { code: '', language: 'text', hasCode: false };
}

const LANG_FROM_WORD = {
  python: 'python', py: 'python', javascript: 'javascript', js: 'javascript',
  typescript: 'typescript', ts: 'typescript', bash: 'bash', shell: 'bash', sh: 'bash',
  sql: 'sql', go: 'go', rust: 'rust', html: 'html', css: 'css', json: 'json', c: 'c', cpp: 'cpp',
};
const FILEPATH_FILLER = new Set([
  'a', 'an', 'the', 'please', 'can', 'you', 'me', 'my', 'for', 'to', 'that', 'which', 'with',
  'and', 'of', 'in', 'on', 'file', 'script', 'program', 'code', 'function', 'func', 'def', 'class',
  'method', 'component', 'simple', 'new', 'create', 'write', 'build', 'make', 'implement', 'generate',
  'add', 'fix', 'prints', 'print', 'returns', 'return', 'using', 'use', 'it', 'its', 'named', 'called',
  'do', 'thing', 'some', 'something',
]);

export function workFilepath(text, language) {
  const raw = String(text || '');
  const explicit = raw.match(/\b([\w-]+\.(?:py|js|jsx|ts|tsx|sh|json|html|css|sql|go|rs|c|cpp|txt|md))\b/i);
  if (explicit) return explicit[1].toLowerCase();
  let lang = language;
  if (!lang) {
    const lw = raw.toLowerCase();
    for (const word of Object.keys(LANG_FROM_WORD)) {
      if (new RegExp(`\\b${word}\\b`).test(lw)) { lang = LANG_FROM_WORD[word]; break; }
    }
  }
  const idMatch = raw.match(/\b(?:function|func|def|class|method|component)\s+([a-z_][\w]*)/i)
    || raw.match(/\b([a-z_][a-z0-9_]{2,})\s*\(/i);
  let slug;
  if (idMatch && !FILEPATH_FILLER.has(idMatch[1].toLowerCase())) {
    slug = idMatch[1].replace(/_/g, '-').toLowerCase();
  } else {
    slug = raw
      .replace(/[^a-z0-9\s]+/gi, ' ')
      .toLowerCase()
      .split(/\s+/)
      .filter((w) => w && !FILEPATH_FILLER.has(w) && !LANG_FROM_WORD[w])
      .slice(0, 3)
      .join('-') || 'work';
  }
  return `${slug}.${LANG_EXT[lang] || 'txt'}`;
}

export function extractStreamingCode(text) {
  const open = /```([\w+-]*)\n?/.exec(String(text || ''));
  if (!open) return { code: '', language: 'text' };
  const after = String(text).slice(open.index + open[0].length);
  const close = after.indexOf('```');
  const code = close >= 0 ? after.slice(0, close) : after;
  return { code, language: open[1] || 'text' };
}

function cleanText(input, maxLen = 8000) {
  return String(input ?? '').slice(0, maxLen);
}

export function useWorkMaterialization({
  setOnline,
  setMilestones,
  chatModelId,
}) {
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState('');

  const msgSeqRef = useRef(0);
  const turnTokenRef = useRef(0);
  const busyRef = useRef(false);
  const abortRef = useRef(null);
  const workTabIdsRef = useRef([]);
  const writingTabIdRef = useRef(null);
  const activeWorkRef = useRef(null);

  const settlePartialWork = useCallback((token, completion) => {
    const active = activeWorkRef.current;
    if (!active || active.token !== token) return;
    activeWorkRef.current = null;
    const snapshot = getTabStoreSnapshot();
    const tab = [...snapshot.tabs, ...(snapshot.recoverableTabs || [])].find((record) => record.id === active.id);
    if (!tab?.content) return;
    updateMaterializedTab(active.id, { content: { ...tab.content, streaming: false, completion } });
    setWorkResultOutcome({ tabId: active.id, completion });
    // Retain real partial work in place. Only an empty placeholder may retire;
    // explicit Close/Reopen continues to own the reader's visibility and identity.
    if (!tab.content.code.trim() && !tab.content.verifyOutput
      && beginRetractingMaterializedTab(active.id)) {
      workTabIdsRef.current = workTabIdsRef.current.filter((id) => id !== active.id);
    }
  }, []);

  const pushMessage = useCallback((role, text, extra) => {
    const id = (msgSeqRef.current += 1);
    setMessages((prev) => [...prev, { id, role, text, ...(extra || {}) }].slice(-MAX_MESSAGES));
    return id;
  }, []);

  const updateMessage = useCallback((id, text) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, text } : m)));
  }, []);

  /* Organ 30: submit a real correction for one message's human-state guess.
   * Optimistic locally (marks `corrected` immediately so the affordance
   * closes without waiting on the network) but the durable ground truth is
   * whatever the backend actually recorded -- a failed request leaves the
   * message's `humanState.corrected` unset so the user can retry.
   *
   * `turnId` must be read from the current `messages` state directly, not
   * from inside the `setMessages` updater -- a real bug caught by live
   * verification: React does not guarantee an updater function runs
   * synchronously before the next line executes, so a closure variable
   * assigned inside it could still be `null` when checked immediately
   * after, silently skipping the actual network call while the optimistic
   * UI still showed "noted" (a correction that was never really recorded). */
  const correctMessageHumanState = useCallback(async (messageId, correctedState) => {
    const turnId = messages.find((m) => m.id === messageId)?.humanState?.turnId;
    if (!turnId) return false;
    setMessages((prev) => prev.map((m) => (
      m.id === messageId && m.humanState
        ? { ...m, humanState: { ...m.humanState, corrected: correctedState } }
        : m
    )));
    const ok = await correctHumanState(turnId, correctedState);
    if (!ok) {
      setMessages((prev) => prev.map((m) => (
        m.id === messageId && m.humanState
          ? { ...m, humanState: { ...m.humanState, corrected: null } }
          : m
      )));
    }
    return ok;
  }, [messages]);

  const stopTurn = useCallback(() => {
    if (!busyRef.current) return;
    const token = turnTokenRef.current;
    // Invalidate callbacks before aborting: even a synchronously delivered
    // abort callback must not mutate the retained result or a subsequent turn.
    turnTokenRef.current += 1;
    settlePartialWork(token, 'cancelled');
    if (abortRef.current) abortRef.current.abort();
    busyRef.current = false;
    setBusy(false);
    releaseWorkMaterialization();
    setConversationPhase('idle');
    publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0, data: { phase: 'stopped' } });
    pushMessage('gagos', 'Generation cancelled locally; backend termination is unconfirmed.');
  }, [pushMessage, settlePartialWork]);

  const submit = useCallback(async (raw) => {
    const text = String(raw ?? '').trim();
    if (!text || busyRef.current) return;
    const workIntent = isWorkIntent(text);

    const token = turnTokenRef.current + 1;
    turnTokenRef.current = token;
    // A new local request supersedes an unfinished approval/replay reader.
    // Retain its partial content and invalidate its callbacks before aborting.
    const heldId = writingTabIdRef.current;
    writingTabIdRef.current = null;
    if (heldId) {
      const previous = getTabStoreSnapshot();
      const held = [...previous.tabs, ...(previous.recoverableTabs || [])].find((record) => record.id === heldId);
      if (held?.content) updateMaterializedTab(heldId, { content: { ...held.content, streaming: false, completion: 'cancelled' } });
    }
    busyRef.current = true;
    setBusy(true);
    setDraft('');
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    const userMsgId = pushMessage('user', sanitizeToText(cleanText(text, 400)));
    const gagosId = null;

    setConversationPhase('thinking');
    setWorkResultOutcome(null);
    publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 1, data: { phase: 'question', text } });
    if (workIntent) {
      publishCognition({ type: 'directive', label: text.slice(0, 80), intensity: 1, source: 'gagos' });
    }

    try {
      if (workIntent) {
        claimWorkMaterialization();
        const writeSeat = selectNextAvailableVertebraSeat(getOccupiedVertebraSeats());
        const writingTab = showContentSurface(
          { code: '', language: 'text', filepath: workFilepath(text), streaming: true },
          getContentSurfacePlacement(writeSeat),
        );
        activeWorkRef.current = { id: writingTab.id, token };
        const retained = getTabStoreSnapshot();
        const records = new Map(retained.tabs.map((tab) => [tab.id, tab]));
        // Count retained surfaces, not submissions. Re-editing a file reuses
        // its ID; duplicate queue entries used to evict that current result.
        workTabIdsRef.current = [
          ...workTabIdsRef.current.filter((id) => id !== writingTab.id
            && records.has(id) && records.get(id).lifecycle !== 'retracting'),
          writingTab.id,
        ];
        while (workTabIdsRef.current.length > 5) {
          const index = workTabIdsRef.current.findIndex((id) => {
            const tab = records.get(id);
            return id !== writingTab.id && id !== retained.focusId
              && tab && !tab.pinned && !tab.content?.streaming && !tab.content?.completion;
          });
          // Five is a retention target, not permission to discard protected
          // work. Explicit dismissal remains available for those surfaces.
          if (index < 0) break;
          const oldest = workTabIdsRef.current[index];
          if (!oldest || !beginRetractingMaterializedTab(oldest)) break;
          workTabIdsRef.current.splice(index, 1);
        }
        // A prompt guess is only a placeholder. Once this request names its
        // actual path, text-only/pathless updates cannot erase that evidence.
        let observedFilepath = '';
        const onWritingChunk = (answer) => {
          if (turnTokenRef.current !== token || activeWorkRef.current?.token !== token) return;
          claimWorkMaterialization();
          const partial = extractStreamingCode(answer);
          if (partial.code && partial.code.trim()) {
            updateMaterializedTab(writingTab.id, {
              content: {
                code: partial.code,
                language: (partial.language || 'text').toLowerCase(),
                filepath: observedFilepath || workFilepath(text),
                streaming: true,
              },
            });
          }
        };

        const onWritingCodeChunk = (code, language, filepath) => {
          if (turnTokenRef.current !== token || activeWorkRef.current?.token !== token) return;
          if (filepath) observedFilepath = filepath;
          claimWorkMaterialization();
          if (!code || !code.trim()) return;
          updateMaterializedTab(writingTab.id, {
            content: {
              code,
              language: (language || 'text').toLowerCase(),
              filepath: observedFilepath || workFilepath(text, language),
              streaming: true,
            },
          });
        };

        const result = await sendDirective(
          text,
          abortRef.current?.signal,
          onWritingChunk,
          onWritingCodeChunk,
        );

        // Cancel already released this turn's claim. A late response cannot
        // release the claim held by a newer submission.
        if (turnTokenRef.current !== token) return;

        if (result?.paused) {
          activeWorkRef.current = null;
          writingTabIdRef.current = writingTab.id;
          const current = getTabStoreSnapshot();
          const held = [...current.tabs, ...(current.recoverableTabs || [])].find((record) => record.id === writingTab.id);
          if (held?.content) {
            // A terminal code snapshot may precede the permission frame
            // without ever triggering the streaming-code callback.
            const fresh = result.emittedCode?.code?.trim() ? result.emittedCode : null;
            const content = fresh ? {
              code: fresh.code, language: fresh.language || held.content.language,
              filepath: fresh.filepath || observedFilepath || held.content.filepath,
            } : held.content;
            updateMaterializedTab(writingTab.id, { content: { ...content, streaming: false, completion: 'awaiting-approval' } });
          }
          setWorkResultOutcome({ tabId: writingTab.id, completion: 'awaiting-approval' });
          claimWorkMaterialization(600000);
          pushMessage('gagos', 'Holding for your approval before I build that.');
        } else {
          // Only this request's returned snapshot can establish its artifact.
          // A concurrent/cancelled stream may change the legacy global cache.
          const fresh = result?.emittedCode?.code ? result.emittedCode : null;
          const extracted = extractWork(result?.answer);
          const code = fresh ? fresh.code : extracted.code;
          const language = fresh ? (fresh.language || 'text').toLowerCase() : extracted.language;
          const hasCode = Boolean((fresh || extracted.hasCode) && code.trim());

          if (isCompleteWorkResult(result, hasCode)) {
            const filepath =
              fresh?.filepath || observedFilepath || workFilepath(text, language);
            const dup = getTabStoreSnapshot().tabs.find(
              (t) =>
                t.kind === 'content' &&
                t.id !== writingTab.id &&
                t.lifecycle !== 'retracting' &&
                t.content?.filepath === filepath,
            );
            const targetId = dup ? dup.id : writingTab.id;
            if (dup) {
              if (beginRetractingMaterializedTab(writingTab.id)) {
                workTabIdsRef.current = workTabIdsRef.current.filter((id) => id !== writingTab.id);
              }
              if (!getTabStoreSnapshot().focusId) focusMaterializedTab(dup.id);
            }
            updateMaterializedTab(targetId, { content: { code, language, filepath, streaming: false } });
            activeWorkRef.current = null;
            pushMessage('gagos', `↳ I've materialized ${filepath} on the spine.`);
          } else {
            if (hasCode) {
              updateMaterializedTab(writingTab.id, { content: {
                code, language, filepath: fresh?.filepath || observedFilepath || workFilepath(text, language), streaming: true,
              } });
            }
            settlePartialWork(token, 'incomplete');
            const replyText = cleanText(stripAlignmentPreamble(result?.answer));
            if (result?.ok && replyText) {
              pushMessage('gagos', replyText);
            } else if (replyText) {
              // Real backend text streamed, but the connection dropped before
              // a terminal frame arrived -- never present a truncated reply as
              // a complete one.
              pushMessage('gagos', `${replyText}\n\n[response interrupted before completion]`);
              setConversationPhase('error');
              publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.4, data: { phase: 'error' } });
            } else {
              pushMessage('gagos', 'COGNITION FAULT: the stream ended before any code or reply arrived.');
              setConversationPhase('error');
              publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.4, data: { phase: 'error' } });
            }
          }
          releaseWorkMaterialization();
          if (isEstablishedTurn(result)) setOnline(true);
        }

        if (getConversationPhase() !== 'error') {
          setConversationPhase('idle');
        }
      } else {
        const reply = await sendVoiceTurn(text, {
          signal: abortRef.current?.signal,
          modelId: chatModelId,
          onChunk: (partial) => {
            if (turnTokenRef.current !== token) return;
            const chunk = cleanText(partial);
            if (chunk) {
              setConversationPhase('streaming');
              publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.82, data: { phase: 'reply', reply: chunk } });
            }
          },
          // Organ 30: advisory only -- never gates the turn, only attaches
          // the guess to the user's own message so a correction affordance
          // can render (and be dismissed) beside it.
          onHumanState: (hypothesis) => {
            if (turnTokenRef.current !== token) return;
            setMessages((prev) => prev.map((m) => (
              m.id === userMsgId ? { ...m, humanState: hypothesis } : m
            )));
          },
        });
        if (turnTokenRef.current !== token) return;
        if (!reply.trim()) {
          pushMessage('gagos', 'COGNITION FAULT: the stream ended before any reply arrived.');
          setConversationPhase('error');
          publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.4, data: { phase: 'error' } });
          return;
        }
        // The conversational reply is a real user-facing result, not only a
        // speech/3D event. Keep it in the DOM conversation log so Guided users
        // and assistive technology can read the same answer that voice speaks.
        pushMessage('gagos', cleanText(reply));
        setConversationPhase('complete');
        setOnline(true);
      }
      if (getConversationPhase() !== 'error') {
        publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.6, data: { phase: 'reply-complete' } });
      }
    } catch (error) {
      if (turnTokenRef.current !== token) return;
      settlePartialWork(token, 'incomplete');
      if (workIntent) releaseWorkMaterialization();
      const isAbort = error instanceof Error && error.name === 'AbortError';
      if (isAbort) {
        setConversationPhase('error');
        pushMessage('gagos', 'Generation interrupted. No completed outcome is established.');
        return;
      }

      const detail = error instanceof Error ? error.message : 'link unavailable';
      const offline = error instanceof TypeError || /failed to fetch|networkerror|load failed|abort/i.test(detail);
      if (offline) setOnline(false);
      const msg = offline
        ? "I can't reach my backend right now. It may be offline; your words are safe, retry when it's back."
        : `That turn was interrupted (${detail}).`;
      if (gagosId) {
        setMessages((prev) => prev.map((m) => (m.id === gagosId ? { ...m, text: msg, retry: text } : m)));
      } else {
        pushMessage('gagos', msg, { retry: text });
      }
      setConversationPhase('error');
      publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.4, data: { phase: 'error' } });
    } finally {
      void fetchOnboardingState().then(setMilestones);
      if (turnTokenRef.current === token) {
        busyRef.current = false;
        setBusy(false);
      }
    }
  }, [pushMessage, setOnline, setMilestones, chatModelId, settlePartialWork]);

  return {
    messages,
    setMessages,
    pushMessage,
    updateMessage,
    correctMessageHumanState,
    busy,
    draft,
    setDraft,
    stopTurn,
    submit,
    writingTabIdRef,
    workTabIdsRef,
    // Read-only generation/signal access for the existing approval consumer.
    // This hook remains the sole writer of request generation and cancellation.
    turnTokenRef,
    getTurnSignal: () => abortRef.current?.signal,
  };
}
