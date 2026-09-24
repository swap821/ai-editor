# GAGOS physical embodiment — live worker boundary

Captured 2026-09-24 against a fresh disposable backend with the default
container execution setting. The temporary operator credential existed only in
the streaming client process and was not printed or persisted in the
repository.

## Request and result

After the normal session, enrollment, login, and reauthentication ceremony, an
authenticated `POST /api/generate` was sent with `swarm=true` and a
non-mutating request:

```json
{
  "modelId": "auto",
  "sessionId": "physical-swarm-boundary",
  "swarm": true,
  "messages": [{"role": "user", "content": [{"text": "Plan this as a bounded worker swarm, but do not write files or execute anything."}]}]
}
```

The live response was `200 text/event-stream; charset=utf-8` and its measured
event sequence was:

`turn.started → alignment → step → plan → error → done`

The error payload was:

```json
{
  "code": "strategy_unavailable",
  "text": "experimental strategy is not production-selected: swarm; route it through WorkerFoundry before enabling"
}
```

The terminal event was `done`. No `swarm_plan`, `caste_start`, `caste_end`,
worker, materialization, write, or execution event appeared. The default
container backend also reported its existing fail-closed Docker-unavailable
warning at startup; it was not reached by this non-mutating strategy refusal.

## Interpretation

This is live evidence that the current backend refuses the experimental swarm
selector before WorkerFoundry owns its worker lifecycle. The gallery's bounded
worker branches and materialization continuity therefore remain deterministic
frontend projections, not claims of a live backend worker/materialization
cycle. No frontend state was changed by this probe, and the branch ceiling is
kept at eight until a real WorkerFoundry path is available.

