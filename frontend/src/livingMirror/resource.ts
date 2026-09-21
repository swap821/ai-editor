import { useEffect, useReducer, useState } from 'react';
import { API_BASE } from '../config';

const EMPTY_REQUEST_INIT: RequestInit = Object.freeze({});

export type ResourceStatus = 'loading' | 'available' | 'empty' | 'unavailable' | 'failed';
export interface Resource<T> {
  status: ResourceStatus;
  data: T | null;
  error: string | null;
  source: string;
  receivedAt: string | null;
}
export class ReadFailure extends Error {
  constructor(message: string, readonly status: 'unavailable' | 'failed') { super(message); }
}
export async function readResource<T>(path: string, parse: (value: unknown) => T, signal?: AbortSignal, init: RequestInit = EMPTY_REQUEST_INIT): Promise<T> {
  let response: Response;
  try { response = await fetch(`${API_BASE}${path}`, { ...init, credentials: 'include', signal }); }
  catch (error) {
    if (signal?.aborted) throw error;
    throw new ReadFailure('Local service could not be reached. Last-known records may be out of date.', 'unavailable');
  }
  if (!response.ok) throw new ReadFailure(response.status === 401 ? 'Connect your operator session to inspect these records.'
    : response.status === 403 ? 'Your current session cannot inspect these records.'
      : `Records could not be read (HTTP ${response.status}).`, [401, 403, 404, 503].includes(response.status) ? 'unavailable' : 'failed');
  let value: unknown;
  try { value = await response.json(); }
  catch { throw new ReadFailure('Records could not be read. The service returned an unsupported response.', 'failed'); }
  try { return parse(value); }
  catch (error) { throw new ReadFailure(error instanceof Error ? error.message : 'Unsupported response', 'failed'); }
}

/** Identity fencing prevents an old mission response appearing under a newly selected one. */
export function useResource<T>(path: string | null, parse: (value: unknown) => T, isEmpty: (data: T) => boolean, init: RequestInit = EMPTY_REQUEST_INIT) {
  const [revision, refresh] = useReducer((n: number) => n + 1, 0);
  const [resource, setResource] = useState<Resource<T> & { requestInit: RequestInit }>({ status: 'loading', data: null, error: null, source: path ?? '', receivedAt: null, requestInit: init });
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setResource((old) => {
      const sameRead = old.source === path && old.requestInit === init;
      return { ...old, source: path, requestInit: init, status: 'loading', error: null,
        data: sameRead ? old.data : null, receivedAt: sameRead ? old.receivedAt : null };
    });
    void readResource(path, parse, controller.signal, init).then((data) => {
      if (!controller.signal.aborted) setResource({ status: isEmpty(data) ? 'empty' : 'available', data, error: null, source: path, receivedAt: new Date().toISOString(), requestInit: init });
    }).catch((error) => {
      if (!controller.signal.aborted) setResource((old) => ({ ...old, status: error instanceof ReadFailure ? error.status : 'failed', error: error.message }));
    });
    return () => controller.abort();
  }, [path, parse, isEmpty, init, revision]);
  // POST-backed reads can share a URL but address different files/records.
  const visible = path === resource.source && resource.requestInit === init ? resource : { status: 'loading' as const, data: null, error: null, source: path ?? '', receivedAt: null };
  return { ...visible, refresh };
}
