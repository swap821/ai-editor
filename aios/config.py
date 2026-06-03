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


# --------------------------------------------------------------------------- #
# Typed environment-variable accessors
# --------------------------------------------------------------------------- #
def _env_str(name: str, default: str) -> str:
    """Return the environment value for *name*, or *default* if unset/blank."""
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    """Return *name* parsed as ``int``; fall back to *default* on absence/error."""
    try:
        return int(_env_str(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Return *name* parsed as ``float``; fall back to *default* on absence/error."""
    try:
        return float(_env_str(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    """Return *name* parsed as a boolean (``true/1/yes/on``), else *default*."""
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


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
#: SQLite database backing the tamper-evident, hash-chained audit trail.
AUDIT_DB_PATH: Final[Path] = DATA_DIR / "aios_audit.db"
#: On-disk FAISS index for semantic/episodic embeddings.
FAISS_INDEX_PATH: Final[Path] = DATA_DIR / "vector_index.faiss"

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

#: Absolute directories the executor may touch. Defaults to the "playground"
#: (``training_ground``) so the agent learns organically without risking the
#: host. Out-of-scope paths auto-escalate to RED in the security gateway.
SCOPE_ROOTS: Final[tuple[Path, ...]] = _env_scope_roots(
    "AIOS_SCOPE_ROOTS", (PROJECT_ROOT / "training_ground",)
)

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
# HTTP API server (FastAPI / uvicorn) + browser CORS
# --------------------------------------------------------------------------- #
#: Interface and port uvicorn binds to when serving the API.
API_HOST: Final[str] = _env_str("AIOS_API_HOST", "127.0.0.1")
API_PORT: Final[int] = _env_int("AIOS_API_PORT", 8000)
#: Browser origins permitted to call the API (the Vite dev server by default).
#: Comma-separated via ``AIOS_CORS_ORIGINS`` to add deployed front-end origins.
API_CORS_ORIGINS: Final[tuple[str, ...]] = tuple(
    o.strip()
    for o in _env_str(
        "AIOS_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
)


__all__ = [
    "PROJECT_ROOT",
    "DATA_DIR",
    "MEMORY_DB_PATH",
    "AUDIT_DB_PATH",
    "FAISS_INDEX_PATH",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "RETRIEVAL_ALPHA_BM25",
    "RETRIEVAL_BETA_FAISS",
    "RETRIEVAL_GAMMA_RECENCY",
    "RETRIEVAL_LAMBDA_DECAY_PER_HOUR",
    "CONFIDENCE_THRESHOLD",
    "MAX_RED_ACTIONS_PER_SESSION",
    "YELLOW_APPROVAL_TIMEOUT_MS",
    "RED_APPROVAL_TIMEOUT_MS",
    "AUDIT_GENESIS_HASH",
    "SCOPE_ROOTS",
    "OLLAMA_HOST",
    "LLM_MODEL",
    "LLM_REQUEST_TIMEOUT_S",
    "LLM_TEMPERATURE",
    "LLM_NUM_CTX",
    "INDEX_CHAT",
    "REFLECT_ON_FAILURE",
    "BEDROCK_REGION",
    "BEDROCK_MODEL",
    "BEDROCK_MAX_TOKENS",
    "BEDROCK_ENABLED",
    "API_HOST",
    "API_PORT",
    "API_CORS_ORIGINS",
]
