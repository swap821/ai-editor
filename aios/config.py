"""Central configuration for the AI OS (``aios``).

This module is the single source of truth for every filesystem path, database
location, vector-index path, retrieval weight, and security threshold used by
the system. Every other module imports its tunables from here so that no value
is duplicated or hard-coded in more than one place.

Environment variables (optionally supplied via a project-root ``.env`` file)
override the defaults, which are tuned for local-first, single-laptop operation
per the AI OS Jarvis Blueprint v4.0.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# Project root + environment loading
# --------------------------------------------------------------------------- #
#: Absolute path to the project root (the parent directory of the ``aios`` pkg).
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

# Load environment overrides from ``<project root>/.env`` if it exists.
# ``load_dotenv`` is a no-op when the file is absent, so this is always safe.
load_dotenv(PROJECT_ROOT / ".env")

#: Config-module logger. Imported early, so it emits to the default stderr sink
#: until ``aios.logging_config.configure_logging()`` attaches the real formatter.
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

#: Recognised boolean strings. Anything else present-but-unparseable is warned.
_BOOL_TRUE: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
_BOOL_FALSE: Final[frozenset[str]] = frozenset({"0", "false", "no", "off"})


def _warn_unparseable(name: str, raw: str, default: object) -> None:
    """Emit a WARNING when an env var is present but cannot be parsed."""
    _LOGGER.warning(
        "Unparseable AIOS env var; using default",
        extra={"var": name, "value": raw, "default": default},
    )


# --------------------------------------------------------------------------- #
# Typed environment-variable accessors
# --------------------------------------------------------------------------- #
def _env_str(name: str, default: str) -> str:
    """Return the environment value for *name*, or *default* if unset/blank."""
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    """Return *name* parsed as ``int``; fall back to *default* on absence/error."""
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        _warn_unparseable(name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    """Return *name* parsed as ``float``; fall back to *default* on absence/error."""
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        _warn_unparseable(name, raw, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    """Return *name* parsed as a boolean (``true/1/yes/on``), else *default*."""
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    norm = raw.strip().lower()
    if norm in _BOOL_TRUE:
        return True
    if norm in _BOOL_FALSE:
        return False
    _warn_unparseable(name, raw, default)
    return default


def _env_path(name: str, default: Path) -> Path:
    """Return *name* as an absolute, user-expanded ``Path``; else *default*."""
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return Path(raw).expanduser().resolve()


def _env_scope_roots(name: str, default: tuple[Path, ...]) -> tuple[Path, ...]:
    """Parse an ``os.pathsep``-delimited list of directories into resolved paths.

    Used for the executor's allow-list of writable roots. Returns *default*
    (the "playground") when the variable is unset, so the agent always has a
    safe place to learn even with no configuration.
    """
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return tuple(
        Path(part).expanduser().resolve()
        for part in raw.split(os.pathsep)
        if part
    )


# --------------------------------------------------------------------------- #
# Filesystem paths
# --------------------------------------------------------------------------- #
#: Directory holding all mutable runtime state (SQLite DBs, FAISS index,
#: rollback snapshots). Created on import so first run never fails on a missing
#: directory.
DATA_DIR: Final[Path] = _env_path("AIOS_DATA_DIR", PROJECT_ROOT / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

#: SQLite database backing the working/episodic/semantic/mistake memory layers.
MEMORY_DB_PATH: Final[Path] = DATA_DIR / "aios_memory.db"
#: Short-lived approval capabilities. Bearer tokens are persisted only as hashes.
APPROVAL_DB_PATH: Final[Path] = DATA_DIR / "aios_approvals.db"
#: SQLite database backing the tamper-evident, hash-chained audit trail.
AUDIT_DB_PATH: Final[Path] = DATA_DIR / "aios_audit.db"
#: On-disk FAISS index for semantic/episodic embeddings.
FAISS_INDEX_PATH: Final[Path] = DATA_DIR / "vector_index.faiss"
#: Git database for the rollback engine's snapshots. Kept UNDER the gitignored
#: DATA_DIR — never inside the tracked sandbox work-tree — so snapshot commits are
#: local scratch state (like the rest of ``data/``) and never reach the project
#: repo. The sandbox stays the git *work-tree*; only its git *database* moves here.
ROLLBACK_DIR: Final[Path] = _env_path("AIOS_ROLLBACK_DIR", DATA_DIR / "rollback")

# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #
#: sentence-transformers model used for all embeddings. 384-dim, CPU-friendly.
EMBEDDING_MODEL: Final[str] = _env_str("AIOS_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
#: Output dimensionality of :data:`EMBEDDING_MODEL` (must match the FAISS index).
EMBEDDING_DIM: Final[int] = _env_int("AIOS_EMBEDDING_DIM", 384)

# --------------------------------------------------------------------------- #
# Hybrid retrieval weights  ->  R = a*BM25 + b*FAISS + g*exp(-lambda*dt_hours)
# --------------------------------------------------------------------------- #
#: Weight of the BM25 lexical score (exact keywords, error codes, file paths).
RETRIEVAL_ALPHA_BM25: Final[float] = _env_float("AIOS_ALPHA_BM25", 0.25)
#: Weight of the FAISS cosine-similarity score (semantic relatedness).
RETRIEVAL_BETA_FAISS: Final[float] = _env_float("AIOS_BETA_FAISS", 0.45)
#: Weight of the temporal-recency term (recent memories rank higher).
RETRIEVAL_GAMMA_RECENCY: Final[float] = _env_float("AIOS_GAMMA_RECENCY", 0.30)
#: Exponential decay constant per hour for the recency term (lambda).
RETRIEVAL_LAMBDA_DECAY_PER_HOUR: Final[float] = _env_float("AIOS_LAMBDA_DECAY", 0.05)

# --------------------------------------------------------------------------- #
# Procedural-skill "pheromone" dynamics  ->  reinforced trails persist, unused
# ones evaporate. Mirrors the retrieval recency term but decays far slower: a
# verified workflow is meant to outlive a single chat memory, so the default
# half-life is ~6 days (lambda 0.005/hr) rather than ~14 hours. Every recorded
# attempt resets a skill's clock (record_attempt bumps updated_at), so repeated
# use keeps a trail fresh while disuse lets it fade from ranking.
# --------------------------------------------------------------------------- #
#: Exponential decay constant per hour for a verified skill's freshness term.
SKILL_LAMBDA_DECAY_PER_HOUR: Final[float] = _env_float("AIOS_SKILL_LAMBDA_DECAY", 0.005)
#: Maximum positive confidence bonus the planner may add for a step matching
#: strong, fresh verified workflows. Bounded so a trusted trail can encourage a
#: step but never single-handedly clear the human-review gate.
SKILL_CONFIDENCE_BONUS_MAX: Final[float] = _env_float("AIOS_SKILL_BONUS_MAX", 0.2)

# Reuse pheromone: when recalled verified trails are injected into a turn's
# context and the turn ends with a verifier verdict, those trails gain reuse
# credit (success) or reuse stain (failure). Reuse counters influence RANKING
# only — promotion to 'verified' reads direct verifier-backed counts alone —
# and the derived reuse factor is asymmetric by design: one failure bites
# roughly as hard as seven successes reward, because in a fail-closed system a
# misleading trail costs more than a missed reuse.
#: Maximum multiplicative ranking boost from accumulated reuse successes.
SKILL_REUSE_BOOST_MAX: Final[float] = _env_float("AIOS_SKILL_REUSE_BOOST_MAX", 0.15)
#: Maximum multiplicative ranking penalty from accumulated reuse failures.
SKILL_REUSE_PENALTY_MAX: Final[float] = _env_float("AIOS_SKILL_REUSE_PENALTY_MAX", 0.60)
#: Saturation constant for reuse successes (higher = slower saturation).
SKILL_REUSE_SUCCESS_K: Final[float] = _env_float("AIOS_SKILL_REUSE_SUCCESS_K", 3.0)
#: Saturation constant for reuse failures (lower than successes: bites faster).
SKILL_REUSE_FAILURE_K: Final[float] = _env_float("AIOS_SKILL_REUSE_FAILURE_K", 1.5)
#: Hard floor for the reuse factor — a stained trail weakens but never zeroes.
SKILL_REUSE_FACTOR_FLOOR: Final[float] = _env_float("AIOS_SKILL_REUSE_FLOOR", 0.25)
#: Net reuse failures (failures - successes) at which a 'verified' trail is
#: quarantined back to 'candidate'; recovery needs a fresh DIRECT verified
#: success through record_attempt.
SKILL_REUSE_DEMOTE_NET_FAILURES: Final[int] = _env_int("AIOS_SKILL_REUSE_DEMOTE_NET", 3)

# Earned autonomy: the evidence->GREEN bridge. A YELLOW action *class* (action
# type + scope-bound target shape) graduates to autonomous execution after this
# many consecutive verifier-backed successes, and is revoked instantly by a
# single verified failure. OFF by default — supervision stays the norm; RED is
# never earnable (the gateway blocks it before this layer, and execute_approved
# re-classifies and refuses RED even when granted).
#: Master switch. While False, every consequential action stays YELLOW (today's
#: behaviour); is_earned() is hard-wired to return False.
EARNED_AUTONOMY_ENABLED: Final[bool] = _env_bool("AIOS_EARNED_AUTONOMY", False)
#: Consecutive verified successes a signature needs before it is auto-approved.
EARNED_AUTONOMY_MIN_SUCCESSES: Final[int] = _env_int("AIOS_EARNED_AUTONOMY_MIN_SUCCESSES", 5)

# Worker swarm (ant-colony orchestration): the dynamic-fan-out generalization of
# the role-pass castes. A decomposer splits a task into independent subtasks, one
# ephemeral gated worker is spawned per subtask (bounded below), and a synthesizer
# composes the results from verifier evidence. Coordination is stigmergic only
# (shared conversation + sandbox + development trails); authority is unchanged.
#: Hard ceiling on workers a single swarm may spawn (bounds fan-out + RAM).
SWARM_MAX_WORKERS: Final[int] = _env_int("AIOS_SWARM_MAX_WORKERS", 4)
#: How many worker legs may run concurrently. Default 1 keeps the existing
#: sequential stigmergy (each worker sees the previous worker's deposit); raise
#: to 2+ for true parallel fan-out on stronger hardware or cloud-burst workers.
SWARM_WORKER_CONCURRENCY: Final[int] = _env_int("AIOS_SWARM_WORKER_CONCURRENCY", 1)
#: Redundancy per subtask. 1 = one worker per subtask. >1 dispatches that many
#: independent replicas and runs a QUORUM caste to pick or reconcile the result.
SWARM_REDUNDANCY: Final[int] = _env_int("AIOS_SWARM_REDUNDANCY", 1)
#: Allow cloud-burst workers. When enabled AND a cloud agent factory is supplied,
#: a CLOUD_BROKER caste labels subtasks as local or cloud; cloud-eligible subtasks
#: run against a remote provider while remaining behind the same executor gate.
SWARM_CLOUD_BURST_ENABLED: Final[bool] = _env_bool("AIOS_SWARM_CLOUD_BURST", False)

# --------------------------------------------------------------------------- #
# Security & human-in-the-loop gating
# --------------------------------------------------------------------------- #
#: Planner steps scoring below this confidence escalate to human review,
#: independent of security-zone classification.
CONFIDENCE_THRESHOLD: Final[float] = _env_float("AIOS_CONFIDENCE_THRESHOLD", 0.72)
#: Maximum RED-zone actions permitted per session before mandatory re-auth.
MAX_RED_ACTIONS_PER_SESSION: Final[int] = _env_int("AIOS_MAX_RED_ACTIONS", 3)
#: One-click approval window for YELLOW-zone actions, in milliseconds.
YELLOW_APPROVAL_TIMEOUT_MS: Final[int] = _env_int("AIOS_YELLOW_TIMEOUT_MS", 60_000)
#: Typed-token confirmation window for RED-zone actions, in milliseconds.
RED_APPROVAL_TIMEOUT_MS: Final[int] = _env_int("AIOS_RED_TIMEOUT_MS", 30_000)

#: Genesis hash for the audit chain (64 zero characters), per the blueprint.
AUDIT_GENESIS_HASH: Final[str] = "0" * 64

#: Opt-in second layer of the prompt-injection shield: an embedding-similarity
#: blocklist that catches paraphrased injections the regex misses. Off by default
#: so the gateway stays pure-regex and torch-free; the API installs it at startup
#: when set. Loads the embedding model on first classify, so enable only with RAM.
INJECTION_VECTOR_SHIELD: Final[bool] = _env_bool("AIOS_INJECTION_VECTOR_SHIELD", False)
#: Cosine-similarity threshold (>=) above which an input counts as a semantic
#: injection. Higher = stricter (fewer false positives, more misses).
INJECTION_VECTOR_THRESHOLD: Final[float] = _env_float("AIOS_INJECTION_VECTOR_THRESHOLD", 0.6)

#: Absolute directories the executor may touch. Defaults to the "playground"
#: (``training_ground``) so the agent learns organically without risking the
#: host. Out-of-scope paths auto-escalate to RED in the security gateway.
SCOPE_ROOTS: Final[tuple[Path, ...]] = _env_scope_roots(
    "AIOS_SCOPE_ROOTS", (PROJECT_ROOT / "training_ground",)
)

#: Command prefix the agent uses to AUTO-VERIFY a just-written sandbox file by
#: running its sibling pytest (tool_agent's force-verify-after-write — evidence
#: over the model's narration). Must stay SCOPE-LEGAL: a BARE runner with no
#: absolute interpreter path, because the security gateway classifies any
#: absolute / ``..`` path in a command as out-of-scope -> RED. The sandbox-
#: relative test path is appended at call time. The default assumes the backend
#: runs with the project venv's ``python`` on PATH (start it from the activated
#: venv); if it isn't, verification simply fails closed — an unrunnable check is
#: reported FAIL/UNVERIFIED, never a false PASS.
VERIFY_RUNNER: Final[str] = _env_str("AIOS_VERIFY_RUNNER", "python -m pytest")
#: Backend for human-approved arbitrary-code commands. ``host`` preserves the
#: local-first default; ``container`` uses the fail-closed Docker runner.
APPROVED_EXECUTION_BACKEND: Final[str] = _env_str(
    "AIOS_APPROVED_EXECUTION_BACKEND", "host"
).strip().lower()
CONTAINER_RUNTIME: Final[str] = _env_str("AIOS_CONTAINER_RUNTIME", "docker")
CONTAINER_IMAGE: Final[str] = _env_str("AIOS_CONTAINER_IMAGE", "aios-executor:local")
CONTAINER_MEMORY_MB: Final[int] = _env_int("AIOS_CONTAINER_MEMORY_MB", 1024)
CONTAINER_CPUS: Final[float] = _env_float("AIOS_CONTAINER_CPUS", 1.0)
CONTAINER_PIDS_LIMIT: Final[int] = _env_int("AIOS_CONTAINER_PIDS_LIMIT", 128)
#: Resource caps applied before/while executing any command.
MAX_COMMAND_CHARS: Final[int] = _env_int("AIOS_MAX_COMMAND_CHARS", 8192)
MAX_COMMAND_OUTPUT_BYTES: Final[int] = _env_int("AIOS_MAX_COMMAND_OUTPUT_BYTES", 1_048_576)

# --------------------------------------------------------------------------- #
# Local LLM (Ollama) — reflection agent + planner
# --------------------------------------------------------------------------- #
#: Base URL of the local Ollama server.
OLLAMA_HOST: Final[str] = _env_str("OLLAMA_HOST", "http://127.0.0.1:11434")
#: Default model for reflection/planning reasoning (strong local reasoner).
LLM_MODEL: Final[str] = _env_str("AIOS_LLM_MODEL", "llama3.1:8b")
#: Per-request timeout (seconds) for local generation.
LLM_REQUEST_TIMEOUT_S: Final[int] = _env_int("AIOS_LLM_TIMEOUT_S", 120)
#: Low temperature keeps structured (JSON) reflection output deterministic.
LLM_TEMPERATURE: Final[float] = _env_float("AIOS_LLM_TEMPERATURE", 0.1)
#: Context window (tokens). A smaller window shrinks the KV cache, which is what
#: lets mid-size models fit on a small GPU (e.g. a 4GB laptop card).
LLM_NUM_CTX: Final[int] = _env_int("AIOS_LLM_NUM_CTX", 4096)

#: When True, each completed chat turn is embedded into L3 semantic memory so
#: future recall is self-reinforcing across sessions. Loads the embedding model
#: alongside the LLM, so set ``AIOS_INDEX_CHAT=false`` on very RAM-tight hosts.
INDEX_CHAT: Final[bool] = _env_bool("AIOS_INDEX_CHAT", True)

#: When True, a command that fails inside the agentic loop triggers the
#: reflection agent to write a structured lesson to the L4 Mistake pool. Costs
#: an extra local LLM call per failure; set ``AIOS_REFLECT_ON_FAILURE=false`` to
#: disable on RAM-tight hosts.
REFLECT_ON_FAILURE: Final[bool] = _env_bool("AIOS_REFLECT_ON_FAILURE", True)

#: When True, every generated turn runs the advisory alignment interpreter —
#: one extra local LLM completion per turn — to build, persist, and stream the
#: shared-understanding frame (plus its diagnostic observation). Set
#: ``AIOS_INTERPRET_ALIGNMENT=false`` on RAM-tight hosts to skip interpretation
#: entirely: chat proceeds without alignment frames, observations, or
#: ask-pauses, while correction/evaluation endpoints keep serving previously
#: recorded state.
INTERPRET_ALIGNMENT: Final[bool] = _env_bool("AIOS_INTERPRET_ALIGNMENT", True)

# --------------------------------------------------------------------------- #
# Cloud LLM (AWS Bedrock) — optional, for when the local GPU can't host a model
# --------------------------------------------------------------------------- #
#: AWS region for Bedrock (e.g. ``us-east-1``). Setting this is the single opt-in
#: that turns Bedrock on — the model below has a sensible default. Credentials are
#: resolved by boto3's default chain: a Bedrock **API key** via
#: ``AWS_BEARER_TOKEN_BEDROCK`` (the new ``ABSK…`` keys), or a profile/role/IAM
#: pair. This module never reads or writes them to disk (no-secret-persistence).
BEDROCK_REGION: Final[str] = _env_str("AIOS_BEDROCK_REGION", "")
#: Bedrock model (or inference-profile) id to run. The key is *auth*; this names
#: *which* model. Defaults to Amazon Nova Lite (cheap, broadly available) so only
#: a region + key are needed; override per account, e.g.
#: ``us.anthropic.claude-3-5-sonnet-20241022-v2:0``.
BEDROCK_MODEL: Final[str] = _env_str("AIOS_BEDROCK_MODEL", "amazon.nova-lite-v1:0")
#: Max output tokens per Bedrock turn.
BEDROCK_MAX_TOKENS: Final[int] = _env_int("AIOS_BEDROCK_MAX_TOKENS", 1024)
#: True when Bedrock is opted in (region set; the model has a default).
BEDROCK_ENABLED: Final[bool] = bool(BEDROCK_REGION and BEDROCK_MODEL)

# --------------------------------------------------------------------------- #
# Cloud LLM (Google Gemini via Vertex AI) — optional frontier provider
# --------------------------------------------------------------------------- #
#: GCP project for Vertex AI. Setting this is the single opt-in that turns Gemini
#: on (the model + location below have sensible defaults). Credentials come from
#: the laptop's ``gcloud`` **Application Default Credentials** (ADC) — no key on
#: disk in the repo; this module never reads or writes secrets. Run
#: ``gcloud auth application-default login`` once and enable Vertex AI on the project.
GEMINI_PROJECT: Final[str] = _env_str("AIOS_GEMINI_PROJECT", "")
#: Vertex AI region serving the model (Gemini is broadly available in us-central1).
GEMINI_LOCATION: Final[str] = _env_str("AIOS_GEMINI_LOCATION", "us-central1")
#: Gemini model id to run. The project is *auth/billing*; this names *which* model.
#: Defaults to 2.5 Flash (fast + cheap + tool-capable); override to e.g.
#: ``gemini-2.5-pro`` for the frontier reasoner.
GEMINI_MODEL: Final[str] = _env_str("AIOS_GEMINI_MODEL", "gemini-2.5-flash")
#: Max output tokens per Gemini turn.
GEMINI_MAX_TOKENS: Final[int] = _env_int("AIOS_GEMINI_MAX_TOKENS", 1024)
#: Gemini 2.5 models *think* by default, silently consuming the output budget — a
#: short cap can return zero text. This bounds that: ``0`` disables thinking
#: (predictable text within budget — the agent-loop default), a positive value
#: caps the thinking tokens, and ``-1`` leaves the model's own dynamic thinking on.
GEMINI_THINKING_BUDGET: Final[int] = _env_int("AIOS_GEMINI_THINKING_BUDGET", 0)
#: True when Gemini is opted in (a GCP project is set; model + location default).
GEMINI_ENABLED: Final[bool] = bool(GEMINI_PROJECT and GEMINI_MODEL)

# --------------------------------------------------------------------------- #
# Cross-provider router policy (the operator-owned privacy/cost boundary)
# --------------------------------------------------------------------------- #
#: The PRIVACY BOUNDARY: which task classes (``coding|reasoning|general|fast``)
#: ``auto`` may route to a *cloud* provider. **Empty by default -> local-first,
#: cloud is never used by auto** (today's behaviour preserved). Comma-separated,
#: e.g. ``reasoning,general``; unknown names are dropped. The router's gate is
#: deterministic — a model can never route a task the operator didn't opt in.
_VALID_ROUTER_TASKS: Final[tuple[str, ...]] = ("coding", "reasoning", "general", "fast")


def _env_router_tasks(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return tuple(
        t.strip().lower()
        for t in raw.split(",")
        if t.strip().lower() in _VALID_ROUTER_TASKS
    )


ROUTER_CLOUD_TASKS: Final[tuple[str, ...]] = _env_router_tasks("AIOS_ROUTER_CLOUD_TASKS", ())
#: When True (default), ``auto`` keeps a local model when one is usable; a genuine
#: capability gap can still escalate an *opted-in* task to a cloud provider.
ROUTER_PREFER_LOCAL: Final[bool] = _env_bool("AIOS_ROUTER_PREFER_LOCAL", True)
#: The highest cost tier ``auto`` may route to (``free|low|high``).
ROUTER_MAX_COST: Final[str] = _env_str("AIOS_ROUTER_MAX_COST", "high").strip().lower()
#: The HYBRID layer: when True (default), a small LOCAL model picks among the
#: policy-allowed candidates (it can re-order preference but never escape the
#: gate; a deterministic fallback covers any non-answer). It only runs when the
#: policy permits 2+ candidates for the task — i.e. once a cloud task class is
#: opted in — so the default local-only path pays ZERO extra latency. Set False
#: to route purely by the deterministic heuristic.
ROUTER_LLM_PICK: Final[bool] = _env_bool("AIOS_ROUTER_LLM_PICK", True)
#: Evidence calibration: how strongly the MEASURED per-(provider,model,task)
#: verified-success rate (from the development tracker) re-ranks ``auto`` route
#: candidates, in ``[0,1]``. ``0`` = pure heuristic; the default blends measured
#: success so the router learns which model performs on this workload. Cold-start
#: signatures (too few attempts) are absent from the metrics, so they always fall
#: back to the heuristic — calibration only ever refines a well-evidenced choice.
ROUTER_CALIBRATION_WEIGHT: Final[float] = max(
    0.0, min(1.0, _env_float("AIOS_ROUTER_CALIBRATION_WEIGHT", 0.4))
)

# --------------------------------------------------------------------------- #
# HTTP API server (FastAPI / uvicorn) + browser CORS
# --------------------------------------------------------------------------- #
#: Interface and port uvicorn binds to when serving the API.
API_HOST: Final[str] = _env_str("AIOS_API_HOST", "127.0.0.1")
API_PORT: Final[int] = _env_int("AIOS_API_PORT", 8000)
#: Optional bearer token protecting every /api/* route. Required by startup
#: policy whenever API_HOST is configured beyond loopback.
API_TOKEN: Final[str] = _env_str("AIOS_API_TOKEN", "")
#: Browser origins permitted to call the API. Defaults cover the loopback dev
#: surfaces only: the Vite dev server (:5173), the production-preview/``npm run
#: showcase`` server (:4173), and the GAG superbrain lab (:3000) used for the
#: lab-first → port review loop. All loopback-only; comma-separated via
#: ``AIOS_CORS_ORIGINS`` to add deployed front-end origins.
API_CORS_ORIGINS: Final[tuple[str, ...]] = tuple(
    o.strip()
    for o in _env_str(
        "AIOS_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173"
        ",http://localhost:4173,http://127.0.0.1:4173"
        ",http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
)


# --------------------------------------------------------------------------- #
# Startup banner
# --------------------------------------------------------------------------- #
def startup_banner() -> dict[str, object]:
    """Return the resolved security-load-bearing config as a structured dict.

    The banner is intentionally one event with flat, serialisable fields so a
    SIEM or operator can see the active posture at a glance. It deliberately
    does **not** include the raw token value — only whether one is configured.
    """
    return {
        "host": API_HOST,
        "port": API_PORT,
        "token_set": bool(API_TOKEN),
        "token_length": len(API_TOKEN),
        "router_cloud_tasks": list(ROUTER_CLOUD_TASKS),
        "earned_autonomy": EARNED_AUTONOMY_ENABLED,
        "scope_roots": [str(p) for p in SCOPE_ROOTS],
    }


__all__ = [
    "PROJECT_ROOT",
    "DATA_DIR",
    "MEMORY_DB_PATH",
    "APPROVAL_DB_PATH",
    "AUDIT_DB_PATH",
    "FAISS_INDEX_PATH",
    "ROLLBACK_DIR",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "RETRIEVAL_ALPHA_BM25",
    "RETRIEVAL_BETA_FAISS",
    "RETRIEVAL_GAMMA_RECENCY",
    "RETRIEVAL_LAMBDA_DECAY_PER_HOUR",
    "SKILL_LAMBDA_DECAY_PER_HOUR",
    "SKILL_CONFIDENCE_BONUS_MAX",
    "SKILL_REUSE_BOOST_MAX",
    "SKILL_REUSE_PENALTY_MAX",
    "SKILL_REUSE_SUCCESS_K",
    "SKILL_REUSE_FAILURE_K",
    "SKILL_REUSE_FACTOR_FLOOR",
    "SKILL_REUSE_DEMOTE_NET_FAILURES",
    "EARNED_AUTONOMY_ENABLED",
    "EARNED_AUTONOMY_MIN_SUCCESSES",
    "SWARM_MAX_WORKERS",
    "SWARM_WORKER_CONCURRENCY",
    "SWARM_REDUNDANCY",
    "SWARM_CLOUD_BURST_ENABLED",
    "CONFIDENCE_THRESHOLD",
    "MAX_RED_ACTIONS_PER_SESSION",
    "YELLOW_APPROVAL_TIMEOUT_MS",
    "RED_APPROVAL_TIMEOUT_MS",
    "AUDIT_GENESIS_HASH",
    "INJECTION_VECTOR_SHIELD",
    "INJECTION_VECTOR_THRESHOLD",
    "SCOPE_ROOTS",
    "VERIFY_RUNNER",
    "APPROVED_EXECUTION_BACKEND",
    "CONTAINER_RUNTIME",
    "CONTAINER_IMAGE",
    "CONTAINER_MEMORY_MB",
    "CONTAINER_CPUS",
    "CONTAINER_PIDS_LIMIT",
    "MAX_COMMAND_CHARS",
    "MAX_COMMAND_OUTPUT_BYTES",
    "OLLAMA_HOST",
    "LLM_MODEL",
    "LLM_REQUEST_TIMEOUT_S",
    "LLM_TEMPERATURE",
    "LLM_NUM_CTX",
    "INDEX_CHAT",
    "REFLECT_ON_FAILURE",
    "INTERPRET_ALIGNMENT",
    "BEDROCK_REGION",
    "BEDROCK_MODEL",
    "BEDROCK_MAX_TOKENS",
    "BEDROCK_ENABLED",
    "GEMINI_PROJECT",
    "GEMINI_LOCATION",
    "GEMINI_MODEL",
    "GEMINI_MAX_TOKENS",
    "GEMINI_THINKING_BUDGET",
    "GEMINI_ENABLED",
    "ROUTER_CLOUD_TASKS",
    "ROUTER_PREFER_LOCAL",
    "ROUTER_MAX_COST",
    "ROUTER_LLM_PICK",
    "ROUTER_CALIBRATION_WEIGHT",
    "API_HOST",
    "API_PORT",
    "API_TOKEN",
    "API_CORS_ORIGINS",
    "startup_banner",
]
