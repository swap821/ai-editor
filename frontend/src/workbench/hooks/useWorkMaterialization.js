import { useCallback, useRef, useState } from 'react';
import {
  sendDirective,
  sendVoiceTurn,
  getLastEmittedCode,
  fetchOnboardingState,
  BACKEND_REDACTION_MARKER_RE,
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
} from '../../superbrain/lib/tabStore';
import {
  getContentSurfacePlacement,
  selectNextAvailableVertebraSeat,
} from '../../superbrain/lib/materializedSurfaceAnchors';
import { sanitizeToText } from '../../utils/sanitizeHtml';

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

  const pushMessage = useCallback((role, text, extra) => {
    const id = (msgSeqRef.current += 1);
    setMessages((prev) => [...prev, { id, role, text, ...(extra || {}) }].slice(-MAX_MESSAGES));
    return id;
  }, []);

  const updateMessage = useCallback((id, text) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, text } : m)));
  }, []);

  const stopTurn = useCallback(() => {
    if (!busyRef.current) return;
    if (abortRef.current) abortRef.current.abort();
    turnTokenRef.current += 1;
    busyRef.current = false;
    setBusy(false);
    releaseWorkMaterialization();
    setConversationPhase('idle');
    publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0, data: { phase: 'stopped' } });
    pushMessage('gagos', 'Turn cancelled.');
  }, [pushMessage]);

  const submit = useCallback(async (raw) => {
    const text = String(raw ?? '').trim();
    if (!text || busyRef.current) return;
    const workIntent = isWorkIntent(text);

    const token = turnTokenRef.current + 1;
    turnTokenRef.current = token;
    busyRef.current = true;
    setBusy(true);
    setDraft('');
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    pushMessage('user', sanitizeToText(cleanText(text, 400)));
    const gagosId = null;

    setConversationPhase('thinking');
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
        workTabIdsRef.current.push(writingTab.id);
        while (workTabIdsRef.current.length > 5) {
          const oldest = workTabIdsRef.current.shift();
          if (oldest) beginRetractingMaterializedTab(oldest);
        }
        const beforeCode = getLastEmittedCode();

        const onWritingChunk = (answer) => {
          if (turnTokenRef.current !== token) return;
          claimWorkMaterialization();
          const partial = extractStreamingCode(answer);
          if (partial.code && partial.code.trim()) {
            updateMaterializedTab(writingTab.id, {
              content: {
                code: partial.code,
                language: (partial.language || 'text').toLowerCase(),
                filepath: workFilepath(text),
                streaming: true,
              },
            });
          }
        };

        const onWritingCodeChunk = (code, language) => {
          if (turnTokenRef.current !== token) return;
          claimWorkMaterialization();
          if (!code || !code.trim()) return;
          updateMaterializedTab(writingTab.id, {
            content: {
              code,
              language: (language || 'text').toLowerCase(),
              filepath: workFilepath(text, language),
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

        if (turnTokenRef.current !== token) {
          releaseWorkMaterialization();
          return;
        }

        if (result?.paused) {
          writingTabIdRef.current = writingTab.id;
          claimWorkMaterialization(600000);
          pushMessage('gagos', 'Holding for your approval before I build that.');
        } else {
          const emitted = getLastEmittedCode();
          const fresh = emitted && emitted !== beforeCode && emitted.code ? emitted : null;
          const extracted = extractWork(result?.answer);
          const code = fresh ? fresh.code : extracted.code;
          const language = fresh ? (fresh.language || 'text').toLowerCase() : extracted.language;
          const hasCode = Boolean((fresh || extracted.hasCode) && code.trim());

          if (hasCode) {
            const filepath =
              (fresh?.filepath ? fresh.filepath.split(/[\\/]/).pop() : '') || workFilepath(text, language);
            const base = filepath.split(/[\\/]/).pop();
            const dup = getTabStoreSnapshot().tabs.find(
              (t) =>
                t.kind === 'content' &&
                t.id !== writingTab.id &&
                t.lifecycle !== 'retracting' &&
                t.content?.filepath?.split(/[\\/]/).pop() === base,
            );
            const targetId = dup ? dup.id : writingTab.id;
            if (dup) {
              beginRetractingMaterializedTab(writingTab.id);
              workTabIdsRef.current = workTabIdsRef.current.filter((id) => id !== writingTab.id);
              focusMaterializedTab(dup.id);
            }
            updateMaterializedTab(targetId, { content: { code, language, filepath, streaming: false } });
            pushMessage('gagos', `↳ I've materialized ${filepath} on the spine.`);
          } else {
            beginRetractingMaterializedTab(writingTab.id);
            workTabIdsRef.current = workTabIdsRef.current.filter((id) => id !== writingTab.id);
            const replyText = cleanText(stripAlignmentPreamble(result?.answer));
            if (replyText) {
              pushMessage('gagos', replyText);
            } else {
              pushMessage('gagos', 'COGNITION FAULT: the stream ended before any code or reply arrived.');
              setConversationPhase('error');
              publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.4, data: { phase: 'error' } });
            }
          }
          releaseWorkMaterialization();
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
        });
        if (turnTokenRef.current !== token) return;
        if (!reply.trim()) {
          pushMessage('gagos', 'COGNITION FAULT: the stream ended before any reply arrived.');
          setConversationPhase('error');
          publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.4, data: { phase: 'error' } });
          return;
        }
        setConversationPhase('complete');
      }
      setOnline(true);
      publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.6, data: { phase: 'reply-complete' } });
    } catch (error) {
      if (turnTokenRef.current !== token) return;
      const isAbort = error instanceof Error && error.name === 'AbortError';
      if (isAbort) return;

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
  }, [pushMessage, setOnline, setMilestones, chatModelId]);

  return {
    messages,
    setMessages,
    pushMessage,
    updateMessage,
    busy,
    draft,
    setDraft,
    stopTurn,
    submit,
    writingTabIdRef,
    workTabIdsRef,
  };
}
