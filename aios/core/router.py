"""Cross-provider, task-aware LLM router — the hybrid "the mind picks the model".

``model_selector`` already routes by *task* (coding / reasoning / general / fast)
but only across **local** Ollama tags. This module generalises that one tier into
a **cross-provider** pick — local (Ollama) + cloud (Bedrock, Gemini, …) — without
touching the agent loop, memory, security, or the verifier. The chosen route is
still only a *proposer*; the cage (gateway -> scope-lock -> approval -> verifier)
decides regardless of who proposed, and RED stays hard-blocked.

The design is **hybrid**, in three deterministic layers + one optional LLM layer:

  1. **POLICY (operator-owned, deterministic).** A :class:`Policy` gates which
     ``(task, provider)`` pairs are even *eligible*: a PRIVACY gate (a cloud
     provider is allowed only for task classes present in ``cloud_tasks``), a COST
     ceiling, and availability. The pure :data:`LOCAL_FIRST` fallback has an
     **empty** ``cloud_tasks`` -> nothing ever leaves the machine; the live API
     layer passes the configured process default instead. **The local LLM can
     never override the policy** — it only chooses *within* the allowed set.
  2. **DETERMINISTIC RANK.** The allowed candidates are scored by a transparent
     heuristic (capability tier, a local-first bias, cost), optionally blended
     with **evidence calibration** — the measured per-(provider, model, task)
     verified-success rate from the audit/dev metrics — so the router learns what
     actually performs on *this* workload. Cold-start falls back to the heuristic.
  3. **LOCAL-LLM PICK (optional, hybrid).** When a ``picker`` callable (a small
     local model) is supplied, it is offered ONLY the policy-allowed, ranked
     candidates and may re-order the preference; its choice is honoured **only if
     it names an allowed candidate**. Anything else -> the deterministic winner.
     So the LLM can express judgement but can never escape the policy, and the
     route is deterministic whenever the picker is absent or declines.

Pure and side-effect-free: providers, policy, metrics, and the picker are all
passed in, so the whole decision is unit-testable with mocks (no network, no
boto3, no Ollama). The live API layer builds :class:`Provider` rows from its
clients and calls :func:`route`; this module never imports a client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from aios.core.model_selector import (
    TASK_CODING,
    TASKS,
    _normalise_task,
    describe_choice,
    select_model,
)

# --- Provider identity -------------------------------------------------------
PROVIDER_OLLAMA = "ollama"
PROVIDER_BEDROCK = "bedrock"
PROVIDER_GEMINI = "gemini"
PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"

#: UI model-id prefixes (``ollama.qwen2.5-coder:7b`` etc.). The router's chosen
#: model is a BARE id/tag; :func:`route_model_id` re-attaches the prefix for the
#: selector/UI, mirroring ``_resolve_local_model`` in the API layer.
_PREFIX = {
    PROVIDER_OLLAMA: "ollama.",
    PROVIDER_BEDROCK: "bedrock.",
    PROVIDER_GEMINI: "gemini.",
    PROVIDER_OPENAI: "openai.",
    PROVIDER_ANTHROPIC: "anthropic.",
}

# --- Privacy + cost tags -----------------------------------------------------
PRIVACY_LOCAL = "local"
PRIVACY_CLOUD = "cloud"

COST_FREE = "free"
COST_LOW = "low"
COST_HIGH = "high"
_COST_ORDER = {COST_FREE: 0, COST_LOW: 1, COST_HIGH: 2}

#: Coarse capability ceiling per provider kind (a frontier cloud model out-reasons
#: a 7B local one). Used only to RANK *already-allowed* candidates — it can never
#: open a gate the policy closed.
_DEFAULT_CAPABILITY = {
    PROVIDER_OLLAMA: 100,
    PROVIDER_BEDROCK: 300,
    PROVIDER_GEMINI: 300,
    PROVIDER_OPENAI: 300,
    PROVIDER_ANTHROPIC: 300,
}
#: Tie-bias that makes a local provider win over an equally-capable cloud one when
#: the policy allows both (local-first preference). Small on purpose: genuine
#: capability/evidence gaps can still escalate to cloud for an opted-in task.
_LOCAL_BIAS = 60.0
#: How strongly measured success re-ranks candidates when calibration is on
#: (``calibration_weight`` in [0,1]); the rest stays the heuristic. A perfect
#: (1.0) success rate can add up to this many points.
_CALIBRATION_SCALE = 240.0


def default_capability(provider: str) -> int:
    """The coarse capability ceiling for *provider* (local 100, cloud 300)."""
    return _DEFAULT_CAPABILITY.get(provider, 100)


@dataclass(frozen=True)
class Provider:
    """A routable LLM provider expressed as **data** (no client — keeps it pure).

    * ``name`` — ``ollama`` | ``bedrock`` | ``gemini`` | ``openai`` | ``anthropic``.
    * ``privacy`` — :data:`PRIVACY_LOCAL` or :data:`PRIVACY_CLOUD`; the privacy
      gate keys off this.
    * ``cost`` — :data:`COST_FREE` / ``COST_LOW`` / ``COST_HIGH`` (coarse).
    * ``available`` — creds present + reachable *now* (e.g. ``BEDROCK_ENABLED``,
      ``OllamaClient`` up). An unavailable provider is never a candidate.
    * ``models`` — the candidate model tags/ids this provider can run now. For
      a local provider these are Ollama tags fed to :func:`select_model`; for a
      cloud provider they are an **ordered** preference list (best first).
    * ``capability`` — overrides :func:`default_capability` if the registry knows
      better (e.g. a frontier vs. a small cloud model).
    """

    name: str
    privacy: str
    cost: str
    available: bool
    models: tuple[str, ...] = ()
    capability: Optional[int] = None

    @property
    def cap(self) -> int:
        return (
            self.capability
            if self.capability is not None
            else default_capability(self.name)
        )


@dataclass(frozen=True)
class Policy:
    """The operator-owned routing policy. **The local LLM cannot override it.**

    * ``cloud_tasks`` — the task classes ALLOWED to leave the machine. Empty means
      local-first and no automatic cloud route. The API wiring passes the
      configured process default, which may be non-empty.
    * ``max_cost`` — the highest cost tier any route may use.
    * ``prefer_local`` — when True (default), a local candidate gets a small bias
      so it wins ties; capability/evidence gaps can still escalate to an allowed
      cloud provider.
    """

    cloud_tasks: frozenset[str] = field(default_factory=frozenset)
    max_cost: str = COST_HIGH
    prefer_local: bool = True


#: Pure fallback policy: cloud disabled (empty ``cloud_tasks``), local-first.
#: The live process usually passes :mod:`aios.config`'s configured policy instead.
LOCAL_FIRST = Policy()


@dataclass(frozen=True)
class Route:
    """A concrete routing decision: run *model* on *provider* for the task."""

    provider: str  # PROVIDER_OLLAMA | PROVIDER_BEDROCK | PROVIDER_GEMINI | PROVIDER_OPENAI | PROVIDER_ANTHROPIC
    model: str  # the bare model id/tag (no provider prefix)
    privacy: str
    cost: str
    reason: str
    score: float = 0.0

    @property
    def model_id(self) -> str:
        """The prefixed UI/selector id (``ollama.x`` / ``bedrock.x`` / ``gemini.x``)."""
        return _PREFIX.get(self.provider, "") + self.model


def policy_allows(policy: Policy, task: str, provider: Provider) -> bool:
    """Whether the deterministic policy permits routing *task* to *provider*.

    Three gates, **all** must pass — PRIVACY (a cloud provider is allowed only for
    a task in ``cloud_tasks``; local is always allowed), COST (the provider's cost
    must not exceed ``max_cost``), and AVAILABILITY. This is the hard boundary the
    local LLM can never cross.
    """
    if not provider.available:
        return False
    if provider.privacy == PRIVACY_CLOUD and task not in policy.cloud_tasks:
        return False
    if _COST_ORDER.get(provider.cost, 99) > _COST_ORDER.get(policy.max_cost, 2):
        return False
    return True


def _best_model_for(
    provider: Provider, task: str, *, require_tools: bool
) -> Optional[str]:
    """The single best model *provider* can run for *task* (or ``None``).

    Local providers defer to :func:`select_model` (the tested local heuristic,
    honouring ``require_tools``); cloud providers take the first of their ordered
    preference list (best-first, already tool-capable via Converse/function-calls).
    """
    if not provider.models:
        return None
    if provider.privacy == PRIVACY_LOCAL:
        return select_model(
            list(provider.models), task=task, require_tools=require_tools
        )
    return provider.models[0]


def _calibrated_score(
    base: float,
    provider: str,
    model: str,
    task: str,
    metrics: Optional[dict],
    weight: float,
) -> tuple[float, Optional[float]]:
    """Blend *base* with measured success; returns ``(score, success_rate|None)``.

    ``metrics`` maps ``(provider, model, task) -> verified-success rate`` in
    ``[0, 1]``. A known rate shifts the score by up to :data:`_CALIBRATION_SCALE`
    times *weight*; an unknown one (cold start) leaves the heuristic untouched, so
    calibration only ever *refines* the deterministic rank, never destabilises it.
    """
    if not metrics or weight <= 0.0:
        return base, None
    rate = metrics.get((provider, model, task))
    if rate is None:
        return base, None
    rate = max(0.0, min(1.0, float(rate)))
    return base * (1.0 - weight) + (base + _CALIBRATION_SCALE * rate) * weight, rate


def candidates(
    task: str,
    providers: Sequence[Provider],
    *,
    policy: Policy = LOCAL_FIRST,
    require_tools: bool = False,
    metrics: Optional[dict] = None,
    calibration_weight: float = 0.0,
) -> list[Route]:
    """All policy-allowed routes for *task*, ranked best-first (deterministic).

    For each provider that passes :func:`policy_allows` and can field a model,
    score = capability (+ local-first bias) optionally blended with evidence
    calibration. Ties break by lower cost, then a stable provider order, then the
    model id — so the ordering is fully determined by the inputs.
    """
    task = _normalise_task(task)
    rows: list[tuple[tuple, Route]] = []
    for prov in providers:
        if not policy_allows(policy, task, prov):
            continue
        model = _best_model_for(prov, task, require_tools=require_tools)
        if not model:
            continue
        base = float(prov.cap)
        if policy.prefer_local and prov.privacy == PRIVACY_LOCAL:
            base += _LOCAL_BIAS
        score, rate = _calibrated_score(
            base, prov.name, model, task, metrics, calibration_weight
        )
        reason = _describe(prov, model, rate)
        route = Route(
            provider=prov.name,
            model=model,
            privacy=prov.privacy,
            cost=prov.cost,
            reason=reason,
            score=round(score, 4),
        )
        # Sort key (descending score; then cheaper, then stable name/model).
        sort_key = (-score, _COST_ORDER.get(prov.cost, 99), prov.name, model)
        rows.append((sort_key, route))
    rows.sort(key=lambda r: r[0])
    return [route for _key, route in rows]


def route(
    task: str,
    providers: Sequence[Provider],
    *,
    policy: Policy = LOCAL_FIRST,
    require_tools: bool = False,
    picker: Optional[Callable[[Sequence[Route]], Optional[str]]] = None,
    metrics: Optional[dict] = None,
    calibration_weight: float = 0.0,
) -> Optional[Route]:
    """Pick one :class:`Route` for *task*, or ``None`` if the policy allows none.

    1. Build the policy-allowed candidates (:func:`candidates`) — the hard gate.
    2. If a *picker* (the local LLM) is given, offer it ONLY those candidates; it
       may re-order preference but its choice is honoured **only when it names an
       allowed candidate** (matched by ``model_id`` or bare ``model``). Otherwise,
       or when the picker is absent/declines, take the deterministic #1.

    The picker is the *only* non-deterministic input; with it absent the result is
    a pure function of ``(task, providers, policy, metrics)``.
    """
    ranked = candidates(
        task,
        providers,
        policy=policy,
        require_tools=require_tools,
        metrics=metrics,
        calibration_weight=calibration_weight,
    )
    return pick_from(ranked, picker=picker)


def pick_from(
    ranked: Sequence[Route],
    *,
    picker: Optional[Callable[[Sequence[Route]], Optional[str]]] = None,
) -> Optional[Route]:
    """Choose one route from an already-ranked candidate list (the pick step of
    :func:`route`, split out so a caller that already computed :func:`candidates`
    can reuse it instead of recomputing the gate+scoring).

    With *picker* absent or declining, returns the deterministic #1. With a picker,
    honours its choice only when it names an allowed candidate (validated here), so
    the picker can re-order preference but never escape the policy. Returns ``None``
    when *ranked* is empty.
    """
    if not ranked:
        return None
    if picker is not None:
        try:
            choice = picker(ranked)
        except Exception:  # noqa: BLE001 - a flaky picker must never break routing
            choice = None
        if choice:
            chosen = _match_choice(str(choice), ranked)
            if chosen is not None:
                return chosen
    return ranked[0]


def route_model_id(chosen: Optional[Route]) -> Optional[str]:
    """The prefixed selector/UI id for *chosen* (``ollama.x`` …), or ``None``."""
    return chosen.model_id if chosen is not None else None


def describe_route(chosen: Route) -> str:
    """A short, human reason for the UI badge (``cloud · gemini · …`` / local)."""
    return chosen.reason


def _describe(provider: Provider, model: str, success_rate: Optional[float]) -> str:
    """One-line rationale: privacy + provider + (local detail) + evidence."""
    parts = [provider.privacy, provider.name]
    if provider.privacy == PRIVACY_LOCAL:
        parts.append(describe_choice(model))
    else:
        parts.append(model)
    if success_rate is not None:
        parts.append(f"{round(success_rate * 100)}% verified")
    return " · ".join(parts)


def _match_choice(choice: str, ranked: Sequence[Route]) -> Optional[Route]:
    """Resolve a picker's string to an allowed candidate (id or bare model)."""
    choice = choice.strip()
    for r in ranked:
        if choice in (r.model_id, r.model):
            return r
    return None


# --- The local-LLM picker (the hybrid layer) --------------------------------
# These are PURE: the prompt the local model sees and the parser for its reply.
# The actual LLM call lives in the API layer (it needs a client); route()'s
# ``picker`` arg accepts the resulting callable. Whatever the model says, the
# choice is still validated against the allowed candidates in :func:`route`, so
# the local LLM can express preference but can NEVER escape the policy gate.
PICKER_SYSTEM = (
    "You are a model-routing assistant for an AI coding agent. You will be given a "
    "task type and an ALLOW-LIST of candidate model ids that policy already permits. "
    "Choose the single best one for the task. Reply with ONLY that exact model id — "
    "no punctuation, no explanation. You may only pick from the list."
)


def picker_prompt(task: str, cands: Sequence[Route]) -> str:
    """Build the selection prompt the local model sees (deterministic)."""
    lines = [f"Task type: {task}", "", "Allow-list (choose exactly one id):"]
    for r in cands:
        lines.append(f"- {r.model_id}  [{r.privacy}, {r.cost}]  — {r.reason}")
    lines.append("")
    lines.append("Reply with only one id from the list above.")
    return "\n".join(lines)


def parse_pick(text: Optional[str], cands: Sequence[Route]) -> Optional[str]:
    """Extract the chosen model id from the local model's free-text *text*.

    Matches the candidate ids/models that actually appear in the reply, longest
    first so a longer id isn't shadowed by a shorter one it contains. Returns the
    prefixed ``model_id`` (so it round-trips through :func:`_match_choice`), or
    ``None`` when nothing matches — which makes :func:`route` fall back to the
    deterministic winner.
    """
    if not text or not text.strip():
        return None
    t = text.strip()
    for r in sorted(cands, key=lambda c: len(c.model_id), reverse=True):
        if r.model_id in t:
            return r.model_id
    for r in sorted(cands, key=lambda c: len(c.model), reverse=True):
        if r.model in t:
            return r.model_id
    return None
