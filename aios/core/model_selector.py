"""Automatic, task-aware model selection — the agent routes by purpose.

The user should not have to know which local model is strongest for what. Given
the models *actually installed* in Ollama and the *kind of task* at hand, this
picks the best fit **deterministically**. It is a transparent HEURISTIC, not a
benchmark:

  * ``coding``    — code edits + the agentic tool loop -> a coder-tuned model.
  * ``reasoning`` — planning / analysis / hard problems -> a reasoning model.
  * ``general``   — chat / Q&A / explanation -> a strong general instruct model.
  * ``fast``      — trivial / quick replies -> the smallest capable model.

Within a task it prefers instruct over base models and breaks ties by parameter
size (smallest wins for ``fast``, largest otherwise). ``require_tools`` drops
models that don't reliably function-call (reasoning-only families and base
models), so the agentic loop never routes itself to a model that can't use its
tools — even when the request *reads* like reasoning.

Pure and side-effect-free (no network, no model load): callers pass the tag list
(e.g. from ``OllamaClient.list_models``) and the inferred task, so the policy
lives in one tested place instead of the UI.
"""
from __future__ import annotations

import re
from typing import Optional

# --- Task categories the agent routes between -------------------------------
TASK_CODING = "coding"
TASK_REASONING = "reasoning"
TASK_GENERAL = "general"
TASK_FAST = "fast"
TASKS = (TASK_CODING, TASK_REASONING, TASK_GENERAL, TASK_FAST)

# --- Model family knowledge (matched as a prefix of the tag's family) -------
_CODER_FAMILIES = (
    "qwen2.5-coder", "qwen3-coder", "qwen2.5coder", "deepseek-coder",
    "codellama", "codestral", "codegemma", "starcoder", "granite-code",
)
# Reasoning / chain-of-thought families. Strong at analysis, but typically POOR
# at function/tool calling -> excluded when require_tools is set.
_REASONING_FAMILIES = (
    "deepseek-r1", "qwq", "marco-o1", "openthinker", "phi4-reasoning",
)
_STRONG_GENERAL = (
    "qwen3", "qwen2.5", "llama3.3", "llama3.1", "mixtral", "mistral-nemo",
    "mistral-small", "gemma2", "command-r", "phi4",
)
_WEAKER_GENERAL = (
    "llama3.2", "llama3", "llama2", "mistral", "gemma", "qwen2", "phi3", "phi",
)
#: Families that do NOT reliably tool-call (the agentic loop must avoid these).
_NON_TOOL_FAMILIES = _REASONING_FAMILIES
# Live release smoke on this host showed the legacy `mistral:7b` family completing
# a read request without calling the required tool. Keep it available for general
# chat, but do not auto-route the agentic loop to it.
_UNRELIABLE_TOOL_FAMILIES = ("mistral",)

#: Substrings marking a model that should never drive the chat/agent loop.
_EXCLUDE_SUBSTR = (
    "embed", "embedding", "bge", "minilm", "gte-", "rerank", "nomic",
    "guard", "vision", "llava", "moondream", "clip",
)

#: A non-instruct base model is a poor chat/tool driver -> demoted below instruct.
_BASE_PENALTY = 250
#: Small bump for tags that explicitly advertise instruct/chat tuning.
_INSTRUCT_BONUS = 40

#: Per-task tier table: task -> {family-kind -> score}. Higher is better for that
#: task. A kind absent from a row falls back to its ``unknown`` floor.
_TIERS: dict[str, dict[str, int]] = {
    TASK_CODING:    {"coder": 300, "strong": 200, "reasoning": 150, "weak": 100, "unknown": 50},
    TASK_REASONING: {"reasoning": 300, "strong": 220, "coder": 180, "weak": 100, "unknown": 50},
    TASK_GENERAL:   {"strong": 300, "coder": 200, "reasoning": 190, "weak": 150, "unknown": 50},
    TASK_FAST:      {"coder": 200, "strong": 200, "weak": 200, "reasoning": 120, "unknown": 60},
}


def _family(tag: str) -> str:
    """The family portion of an Ollama tag (``qwen2.5-coder:3b`` -> family)."""
    return tag.split(":", 1)[0].lower()


def _matches(fam: str, families: tuple[str, ...]) -> bool:
    return any(fam.startswith(f) for f in families)


def _kind(tag: str) -> str:
    """Coarse family kind: ``coder|reasoning|strong|weak|unknown``."""
    fam = _family(tag)
    if _matches(fam, _CODER_FAMILIES):
        return "coder"
    if _matches(fam, _REASONING_FAMILIES):
        return "reasoning"
    if _matches(fam, _STRONG_GENERAL):
        return "strong"
    if _matches(fam, _WEAKER_GENERAL):
        return "weak"
    return "unknown"


def is_coder(tag: str) -> bool:
    return _kind(tag) == "coder"


def is_reasoning(tag: str) -> bool:
    return _kind(tag) == "reasoning"


def is_base_model(tag: str) -> bool:
    """A non-instruct 'base'/'text' completion model (weak at chat + tools)."""
    n = tag.lower()
    return any(t in n for t in ("-base", ":base", "base-", "-text-", ":text"))


def is_tool_capable(tag: str) -> bool:
    """Whether *tag* can reliably function-call (i.e. drive the agentic loop).

    Reasoning-only families (chain-of-thought models) and base models are not.
    """
    return supports_tool_protocol(tag) and _family(tag) not in _UNRELIABLE_TOOL_FAMILIES


def supports_tool_protocol(tag: str) -> bool:
    """Whether policy considers *tag* compatible with this agent's tool schema.

    Ollama metadata alone is insufficient because some models advertise tools
    but reject or ignore this agent's actual tool request.
    """
    family = _family(tag)
    return (
        not _matches(family, _NON_TOOL_FAMILIES)
        and not is_base_model(tag)
        and not is_excluded(tag)
    )


def parse_size_b(tag: str) -> float:
    """Parameter count in billions parsed from a tag (``:7b`` -> 7.0; 0.0 if none)."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*b(?![a-z0-9])", tag.lower())
    return float(match.group(1)) if match else 0.0


def is_excluded(tag: str) -> bool:
    """Whether *tag* is an embedder/vision/guard model unfit to drive the loop."""
    n = tag.lower()
    return any(x in n for x in _EXCLUDE_SUBSTR)


def _normalise_task(task: Optional[str]) -> str:
    t = (task or TASK_CODING).strip().lower()
    return t if t in TASKS else TASK_CODING


def _score(tag: str, task: str) -> tuple[int, float, str]:
    """Sort key (higher is better) for *tag* under *task*."""
    quality = _TIERS[task].get(_kind(tag), _TIERS[task]["unknown"])
    if is_base_model(tag):
        quality -= _BASE_PENALTY
    elif any(t in tag.lower() for t in ("instruct", "-it", "chat")):
        quality += _INSTRUCT_BONUS
    size = parse_size_b(tag)
    # 'fast' wants the SMALLEST capable model; every other task prefers larger.
    size_key = -size if task == TASK_FAST else size
    return (quality, size_key, tag)


def select_model(
    installed: object, *, task: str = TASK_CODING, require_tools: bool = False
) -> Optional[str]:
    """Pick the best installed model for *task*, or ``None`` if none usable.

    *installed* is a list of Ollama tags. Selection is deterministic: drop
    embedding/vision models (and, when *require_tools*, models that can't
    function-call — reasoning-only families and base models), then rank by the
    per-task capability tier, demoting base below instruct, breaking ties by size
    (smallest first for ``fast``, largest otherwise). Returns ``None`` when
    nothing usable remains, so the caller can fall back to its configured default.
    """
    task = _normalise_task(task)
    usable = [
        m for m in (installed or [])
        if isinstance(m, str) and m.strip() and not is_excluded(m)
    ]
    if require_tools:
        usable = [m for m in usable if is_tool_capable(m)]
    if not usable:
        return None
    return max(usable, key=lambda m: _score(m, task))


def describe_choice(tag: str) -> str:
    """A short, human reason for why *tag* was auto-selected (for the UI badge)."""
    kind = {
        "coder": "coder-tuned", "reasoning": "reasoning",
        "strong": "general", "weak": "general", "unknown": "general",
    }[_kind(tag)]
    parts = [kind]
    size = parse_size_b(tag)
    if size:
        parts.append(f"{size:g}B")
    parts.append("base" if is_base_model(tag) else "instruct")
    return ", ".join(parts)


# --- Task inference from the user's message ---------------------------------
_CODING_HINTS = (
    r"\bfix\b", r"\bbug\b", r"\bdebug\b", r"\berror\b", r"\bexception\b",
    r"\btraceback\b", r"\bedit\b", r"\brefactor\b", r"\bimplement\b",
    r"\bfunction\b", r"\bclass\b", r"\bmethod\b", r"\btests?\b", r"\bcode\b",
    r"\bcompile\b", r"\bsyntax\b", r"\bregex\b", r"\bedit_file\b", r"```",
    r"\.py\b", r"\.js\b", r"\.ts\b", r"\.jsx\b", r"\.tsx\b", r"\.css\b",
    r"\bgit\b", r"\bnpm\b", r"\bpytest\b",
)
_REASONING_HINTS = (
    r"\bwhy\b", r"\banaly[sz]e\b", r"\breason\b", r"\bplan\b", r"\bstrateg",
    r"\bdesign\b", r"\bcompare\b", r"\btrade-?offs?\b", r"\bprove\b",
    r"\bthink through\b", r"\bstep[- ]by[- ]step\b", r"\barchitect",
    r"\bpros and cons\b", r"\bevaluate\b", r"\bshould i\b",
)


def infer_task(text: Optional[str]) -> str:
    """Infer the task category from the latest user message (deterministic).

    Coding is checked first — it is the agentic IDE loop's primary purpose and
    the safest default when a request mixes signals — then reasoning, else
    general. The caller still applies ``require_tools`` so a reasoning-leaning
    request never lands the *tool loop* on a non-tool-calling model.
    """
    t = (text or "").lower()
    if not t.strip():
        return TASK_GENERAL
    if any(re.search(p, t) for p in _CODING_HINTS):
        return TASK_CODING
    if any(re.search(p, t) for p in _REASONING_HINTS):
        return TASK_REASONING
    return TASK_GENERAL
