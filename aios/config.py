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
]
