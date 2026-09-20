"""Cloud model catalog — route across the MANY models a provider offers.

By default the cross-provider router routes among **one** model per cloud provider
(the configured ``BEDROCK_MODEL`` / ``GEMINI_MODEL``). The operator's point: AWS and
Vertex each offer many models — the library shouldn't be limited to one. This
expands the candidate set to the provider's **actual catalog**, discovered once per
process from the live client (the account's invocable Bedrock models / the project's
Gemini models), so ``auto`` + failover + evidence-calibration pick across the breadth.

Discovery is account-accurate (a model only appears if the client lists it as
invocable), so a frontier model is offered only where it can actually run — and the
failover cascade rides past any that still error. Capability here is a coarse
heuristic (refined by calibration); a small bonus keeps the operator's configured
default a strong, known-good cold-start option.
"""

from __future__ import annotations

from typing import Any
import re

#: Capability-tier keywords, matched against TOKENS of the model id rather than
#: as substrings.
#:
#: The substring form had a collision class its own comment documented -- "mini"
#: lives inside "gemini" -- and worked around it by hand-excluding keywords. It
#: missed one: "3b" lives inside "a3b", so `qwen.qwen3-next-80b-a3b`, an 80B
#: model, scored 250 as a LIGHT variant. Measured 2026-09-13 against a live
#: 42-model Bedrock catalog.
#:
#: Splitting the id on non-alphanumerics removes the whole class rather than the
#: instances: "gemini" never yields a "mini" token, and "a3b" never yields "3b".
_FRONTIER = ("opus", "pro", "gpt4", "ultra", "sonnet", "405b")
_STRONG = ("flash", "large", "mixtral")
_LIGHT = ("haiku", "lite", "mini", "nano", "small", "tiny")

#: Families whose ids carry no parameter count but which are current frontier
#: work. Without these, 23 of the 42 models in that catalog -- glm-5,
#: kimi-k2-thinking, deepseek-v3.2 among them -- fell through to the 290
#: "unknown" default and ranked BELOW a 2024 Claude 3 Sonnet.
_FRONTIER_FAMILIES = ("glm", "kimi", "k2", "deepseek", "grok", "command")

#: Parameter count -> score. The most objective signal a model id carries, and
#: the one that keeps working for families nobody has added to a table yet.
_SIZE_TIERS = ((400, 360), (200, 350), (60, 340), (30, 300), (10, 280))

_SIZE_TOKEN = re.compile(r"^(\d+)b$")


def _tokens(model_id: str) -> set[str]:
    """The id split into comparable tokens, lowercased.

    `us.anthropic.claude-3-5-sonnet-20241022-v2:0` ->
    {us, anthropic, claude, 3, 5, sonnet, 20241022, v2, 0}
    """
    return {t for t in re.split(r"[^a-z0-9]+", model_id.lower()) if t}


def _declared_parameters(tokens: set[str]) -> int:
    """Largest parameter count the id declares, in billions, or 0.

    Takes the MAX rather than the first: a mixture-of-experts id names both its
    total and its active parameters (`qwen3-coder-480b-a35b`), and total size is
    the better capability signal of the two.
    """
    sizes = [int(m.group(1)) for t in tokens if (m := _SIZE_TOKEN.match(t))]
    return max(sizes) if sizes else 0


def cloud_capability(model_id: str) -> int:
    """Coarse capability score for a cloud *model_id* (calibration refines it).

    Ordered so the strongest available signal wins:

    1. an explicit LIGHT marker -- a vendor calling its own build "lite", "mini"
       or "nano" is the clearest statement of tier there is;
    2. `sonnet`/`opus`, which name a tier rather than a generation;
    3. a DECLARED PARAMETER COUNT, the most objective signal an id carries;
    4. frontier/strong keywords;
    5. a current frontier family with no size in its name.

    Size is checked before the `_STRONG` keywords on purpose:
    `mistral-large-3-675b-instruct` scored 300 on the word "large" while a 675B
    model plainly out-ranks that tier.

    The band (250-360) is deliberately unchanged. Cloud scores compose with
    `_LOCAL_BIAS` and `_CALIBRATION_SCALE` in the router, so widening it here
    would quietly re-weight local-versus-cloud routing -- a policy change
    wearing a heuristic's clothes. This function only fixes ordering WITHIN
    cloud candidates.
    """
    tokens = _tokens(model_id)

    if tokens & set(_LIGHT):
        return 250
    if "sonnet" in tokens or "opus" in tokens:
        return 360

    parameters = _declared_parameters(tokens)
    if parameters:
        for floor, score in _SIZE_TIERS:
            if parameters >= floor:
                return score
        return 255

    if tokens & set(_FRONTIER):
        return 340
    if tokens & set(_STRONG):
        return 300
    if tokens & set(_FRONTIER_FAMILIES):
        return 340
    return 290  # unknown cloud model -- assume broadly capable


#: What a model id says about the work it was BUILT for. Capability answered
#: "how strong", and nothing answered "strong at what" -- so `cloud_capability`
#: returned one number used for all five task classes, and a code-specialised
#: model and a reasoning model ranked identically for every job. The local side
#: has had this since the beginning (`model_selector._TIERS` maps family-kind to
#: a per-task score); the cloud side simply never got it, which is why "route
#: each model to the task it was designed for" could not be expressed.
#:
#: Matched against TOKENS, never substrings -- the same discipline the tier
#: keywords above had to learn the hard way ("mini" inside "gemini").
#: Keys are TASK names, not family names. Keying them on the family
#: ("coder") was a silent no-op: the task class is "coding", so the equality
#: check in `task_affinity` never fired and every affinity was zero -- a table
#: that looks like a feature and does nothing, which is the exact defect this
#: whole arc has been removing. A test pins every key against the task list.
_KIND_TOKENS: dict[str, tuple[str, ...]] = {
    "coding": ("coder", "code", "codestral", "devstral", "codex", "starcoder"),
    "reasoning": (
        "reasoning",
        "reasoner",
        "thinking",
        "think",
        "r1",
        "o1",
        "o3",
        "qwq",
    ),
    "vision": ("vision", "vl", "vlm", "image", "pixtral"),
    "long_context": ("128k", "200k", "256k", "1m", "longcontext"),
}

#: Deliberately smaller than the router's ``_LOCAL_BIAS`` (60). Affinity re-orders
#: candidates WITHIN the cloud tier; it must not be able to flip a local-versus-
#: cloud decision, because that is a privacy question and privacy is the policy's
#: to decide, not a heuristic's. Same reasoning as the band note above: a scoring
#: change large enough to move a policy boundary is a policy change wearing a
#: heuristic's clothes.
TASK_AFFINITY_BONUS = 40


def model_kind(model_id: str) -> str:
    """What *model_id* advertises itself as built for (``general`` if it says nothing).

    Read off the id and nothing else. A model that does not announce a
    specialism is not penalised for it -- ``general`` simply earns no affinity
    either way, so an uncharacterised frontier model still out-ranks a small
    specialist on raw capability.
    """
    tokens = _tokens(model_id)
    for task, markers in _KIND_TOKENS.items():
        if tokens & set(markers):
            return task
    return "general"


def task_affinity(model_id: str, task: str) -> int:
    """Bonus for a model serving the task it was built for; 0 otherwise.

    Only ever a BONUS, never a penalty. A penalty would mean a coder model is
    actively worse at reasoning than an unlabelled one of the same size, which
    the id does not say and this module has no evidence for. Evidence-based
    re-ranking is calibration's job, and calibration already outweighs this by
    six to one (``_CALIBRATION_SCALE`` is 240) -- so measured performance always
    beats a guess read off a name.
    """
    if not task:
        return 0
    return TASK_AFFINITY_BONUS if model_kind(model_id) == task.strip().lower() else 0


#: Capability bump for the operator's configured default — a known-good model the
#: account can definitely invoke, so cold-start prefers it before evidence exists.
DEFAULT_BONUS = 20
#: Re-discover the cloud catalog every 5 minutes so newly enabled models appear and
#: recently removed models disappear without a process restart.
CATALOG_TTL_SECONDS = 300

_CACHE: dict[str, tuple[list[str], float]] = {}


def catalog_models(client: Any, provider_name: str, default_model: str) -> list[str]:
    """The provider's invocable model ids (discovered once, cached per process).

    Always includes *default_model* (first). Falls back to ``[default_model]`` on any
    discovery error/empty — so a turn is never broken by discovery, and a working
    multi-model discovery is cached while a bare fallback is not (a later real
    discovery can still replace it). The cache expires after ``CATALOG_TTL_SECONDS``
    so model additions/removals are reflected without a restart.
    """
    import time

    now = time.time()
    cached = _CACHE.get(provider_name)
    if cached is not None:
        ids, cached_at = cached
        if now - cached_at < CATALOG_TTL_SECONDS:
            return ids
        _CACHE.pop(provider_name, None)
    ids: list[str] = []
    try:
        for m in client.list_models() or []:
            mid = m.get("id") if isinstance(m, dict) else None
            if mid:
                ids.append(str(mid))
    except Exception:  # noqa: BLE001 - discovery must never break a turn
        ids = []
    if default_model and default_model not in ids:
        ids.insert(0, default_model)
    if not ids:
        ids = [default_model] if default_model else []
    if len(ids) > 1:  # only cache a real multi-model discovery
        _CACHE[provider_name] = (ids, now)
    return ids


def clear_catalog_cache() -> None:
    """Drop the discovery cache (tests; or to force a re-discovery)."""
    _CACHE.clear()
