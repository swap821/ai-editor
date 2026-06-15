import { useState, useEffect, useRef, useCallback } from 'react';
import { API_HEADERS } from '../config';
import { subscribeCognition } from '../superbrain/lib/cognitionBus';

/* ─── useOrganFetch · honest truth-state fetch+subscribe for the organs ─────────
   One reusable hook so every read-only organ surfaces the SAME five honest phases
   instead of hand-rolling its own (and silently failing). It NEVER fabricates: the
   data it returns is exactly what `onData(json)` produced from the real backend
   response — this hook adds STATES, it does not change the data flow.

   The five truth-states (strict — EMPTY ≠ OFFLINE ≠ ERROR):
     loading → mount; no data rendered yet (accessible label on the skeleton).
     ready   → response.ok AND onData(json) produced non-empty data.
     empty   → response.ok BUT onData(json) is falsy / a zero-length array.
               The network succeeded and the backend answered — there are just no
               results yet. This is a calm, honest "nothing here", NOT an error.
     offline → the network fetch failed (rejected / aborted / timed out), OR a
               non-5xx not-ok response (e.g. a transient gateway hiccup). The link
               is down; we keep the last-known data if we ever had any.
     error   → response.status >= 500 (a real backend error) or malformed JSON.
               We surface the status code so the operator sees the truth.

   Cold-offline (W2-5): the mount-time fetch has a 4s AbortController timeout. If it
   times out (or fails) on a FIRST load with no prior data, the phase becomes
   'offline' and `hadData` stays false — so the organ shows the OFFLINE placeholder
   immediately, never "loading forever".

   keep-last (hadData): once ANY fetch has succeeded, a later offline/error keeps the
   last-rendered data and the organ shows a quiet "· link offline" tag instead of a
   placeholder. `hadData` is exposed so the organ can choose first-load-placeholder
   vs keep-last.

   Live refresh: pass cognition-bus event matchers in `events`; the hook re-fetches
   (debounced) when a matching event fires. Matchers may be:
     'SYNTHESIS COMPLETE'            → matches e.type === ... OR e.label === ...
     'synthesis/SYNTHESIS COMPLETE'  → matches e.type === 'synthesis' AND e.label === '...'

   Custom request: `init` lets a caller keep its REAL request shape — the organs POST
   { sessionId, limit } with a JSON body, so they pass `init` as a function returning
   the per-call fetch options (re-evaluated each fetch so a fresh session id is read).
   ──────────────────────────────────────────────────────────────────────────── */

const DEFAULT_TIMEOUT_MS = 4000;
const REFETCH_DEBOUNCE_MS = 500;

/** Does a cognition-bus event match one of the caller's event matchers? */
function eventMatches(e, matchers) {
  if (!e) return false;
  return matchers.some((evt) => {
    if (typeof evt !== 'string') return false;
    if (evt.includes('/')) {
      // 'type/label' → require BOTH (the organs' synthesis/SYNTHESIS COMPLETE form).
      const slash = evt.indexOf('/');
      const type = evt.slice(0, slash);
      const label = evt.slice(slash + 1);
      return e.type === type && String(e.label || '') === label;
    }
    // Bare token → match either the type or the label.
    return e.type === evt || String(e.label || '') === evt;
  });
}

/**
 * @param {string} url  the REAL backend endpoint.
 * @param {object} [opts]
 * @param {string[]} [opts.events]  cognition-bus matchers that trigger a re-fetch.
 * @param {(json:unknown)=>unknown} [opts.onData]  map the raw JSON to display data;
 *        a falsy / zero-length return ⇒ phase='empty' (distinct from offline/error).
 * @param {() => RequestInit} [opts.init]  per-call fetch options (method/body/headers).
 *        Defaults to a GET with the product API headers. A function so a fresh
 *        session id / body is read on every (re)fetch.
 * @param {number} [opts.timeoutMs]  mount/refetch timeout before we call it offline.
 * @returns {{ data: unknown, phase: 'loading'|'ready'|'empty'|'offline'|'error',
 *             hadData: boolean, isError: boolean, error: Error|null,
 *             refetch: () => Promise<void> }}
 */
export function useOrganFetch(url, { events = [], onData = null, init = null, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const [data, setData] = useState(null);
  const [phase, setPhase] = useState('loading');
  const [error, setError] = useState(null);
  // hadData is render-state (a prior fetch ever SUCCEEDED) so the organ can pick
  // first-load-placeholder vs keep-last; the ref mirror lets async closures read it
  // without a re-subscribe.
  const [hadData, setHadData] = useState(false);

  // Mirror state into refs so the bus listener / debounce close over live values
  // without re-subscribing on every render.
  const hadDataRef = useRef(false);
  const onDataRef = useRef(onData);
  const initRef = useRef(init);
  const mountedRef = useRef(true);
  const abortRef = useRef(null);
  const debounceRef = useRef(0);
  onDataRef.current = onData;
  initRef.current = init;

  const doFetch = useCallback(async () => {
    // Cancel any in-flight request so a slow prior fetch can't clobber a newer one.
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const reqInit = typeof initRef.current === 'function'
        ? initRef.current()
        : (initRef.current || { headers: API_HEADERS });
      const r = await fetch(url, { signal: controller.signal, ...reqInit });
      clearTimeout(timeoutId);
      if (!mountedRef.current) return;

      if (!r.ok) {
        // 5xx = a real backend error (surface the code); anything else not-ok is
        // treated as a link problem (offline) — keep last data either way.
        if (r.status >= 500) {
          setError(new Error(`Backend error ${r.status}`));
          setPhase('error');
        } else {
          setError(null);
          setPhase('offline');
        }
        return;
      }

      let json;
      try {
        json = await r.json();
      } catch (parseErr) {
        if (!mountedRef.current) return;
        setError(new Error(`Malformed response: ${parseErr.message}`));
        setPhase('error');
        return;
      }
      if (!mountedRef.current) return;

      const processed = onDataRef.current ? onDataRef.current(json) : json;
      const isEmpty = !processed || (Array.isArray(processed) && processed.length === 0);
      setData(processed);
      hadDataRef.current = true; // a fetch SUCCEEDED — even an empty one counts.
      setHadData(true);
      setError(null);
      setPhase(isEmpty ? 'empty' : 'ready');
    } catch (err) {
      clearTimeout(timeoutId);
      if (!mountedRef.current) return;
      if (err && err.name === 'AbortError') {
        // Timeout or an explicit supersede. A supersede is silent; a mount/refetch
        // timeout is the honest cold-offline signal.
        if (controller === abortRef.current) {
          setError(null);
          setPhase('offline');
        }
        return;
      }
      // A network-layer throw (TypeError: failed to fetch, DNS, CORS) = offline.
      setError(null);
      setPhase('offline');
    }
  }, [url, timeoutMs]);

  const refetch = useCallback(() => doFetch(), [doFetch]);

  // Mount-time fetch (+ re-fetch if the url/init signature changes).
  useEffect(() => {
    mountedRef.current = true;
    setPhase('loading');
    doFetch();
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      clearTimeout(debounceRef.current);
    };
  }, [doFetch]);

  // Live refresh — debounced so a burst of bus events can't hammer the backend.
  useEffect(() => {
    if (!events || events.length === 0) return undefined;
    const unsub = subscribeCognition((e) => {
      if (!eventMatches(e, events)) return;
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        if (mountedRef.current) void doFetch();
      }, REFETCH_DEBOUNCE_MS);
    });
    return () => {
      unsub();
      clearTimeout(debounceRef.current);
    };
    // events is provided as a stable literal by the organs; join() guards identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events.join('|'), doFetch]);

  return {
    data,
    phase,
    hadData,
    isError: phase === 'error',
    error,
    refetch,
  };
}
