from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent


def _worker_sandbox_active() -> bool:
    """True inside a Council Runtime worker subprocess.

    ``ControlledSubprocessBackend`` scrubs every secret from the worker's
    environment and sets ``AIOS_WORKER_SANDBOX=1``. Re-reading ``.env`` here
    would re-inject the very secrets the spawner stripped, so dotenv loading is
    suppressed when this flag is present.
    """
    return os.getenv("AIOS_WORKER_SANDBOX", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


if not _worker_sandbox_active():
    load_dotenv(PROJECT_ROOT / ".env")

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

_BOOL_TRUE: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
_BOOL_FALSE: Final[frozenset[str]] = frozenset({"0", "false", "no", "off"})


def _warn_unparseable(name: str, raw: str, default: object) -> None:
    _LOGGER.warning(
        "Unparseable AIOS env var; using default",
        extra={"var": name, "value": raw, "default": default},
    )


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        _warn_unparseable(name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        _warn_unparseable(name, raw, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
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
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return Path(raw).expanduser().resolve()


def _env_scope_roots(name: str, default: tuple[Path, ...]) -> tuple[Path, ...]:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return tuple(
        Path(part).expanduser().resolve()
        for part in raw.split(os.pathsep)
        if part
    )


DATA_DIR: Final[Path] = _env_path("AIOS_DATA_DIR", PROJECT_ROOT / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

MEMORY_DB_PATH: Final[Path] = DATA_DIR / "aios_memory.db"
APPROVAL_DB_PATH: Final[Path] = DATA_DIR / "aios_approvals.db"
AUDIT_DB_PATH: Final[Path] = DATA_DIR / "aios_audit.db"
FAISS_INDEX_PATH: Final[Path] = DATA_DIR / "vector_index.faiss"
ROLLBACK_DIR: Final[Path] = _env_path("AIOS_ROLLBACK_DIR", DATA_DIR / "rollback")
COUNCIL_RUNTIME_DIR: Final[Path] = _env_path(
    "AIOS_COUNCIL_RUNTIME_DIR", DATA_DIR / "council_runtime"
)
COUNCIL_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

EMBEDDING_MODEL: Final[str] = _env_str("AIOS_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIM: Final[int] = _env_int("AIOS_EMBEDDING_DIM", 384)

RETRIEVAL_ALPHA_BM25: Final[float] = _env_float("AIOS_ALPHA_BM25", 0.25)
RETRIEVAL_BETA_FAISS: Final[float] = _env_float("AIOS_BETA_FAISS", 0.45)
RETRIEVAL_GAMMA_RECENCY: Final[float] = _env_float("AIOS_GAMMA_RECENCY", 0.30)
RETRIEVAL_LAMBDA_DECAY_PER_HOUR: Final[float] = _env_float("AIOS_LAMBDA_DECAY", 0.05)

MEMORY_COMPACT_UNVERIFIED_CHAT_DAYS: Final[float] = _env_float(
    "AIOS_MEMORY_COMPACT_UNVERIFIED_CHAT_DAYS", 7.0
)
MEMORY_COMPACT_EPISODIC_DAYS: Final[float] = _env_float(
    "AIOS_MEMORY_COMPACT_EPISODIC_DAYS", 30.0
)
MEMORY_COMPACT_SEMANTIC_MAX_PER_TYPE: Final[int] = _env_int(
    "AIOS_MEMORY_COMPACT_SEMANTIC_MAX_PER_TYPE", 5_000
)
MEMORY_COMPACT_WORKING_IDLE_MINUTES: Final[int] = _env_int(
    "AIOS_MEMORY_COMPACT_WORKING_IDLE_MINUTES", 60
)

SKILL_LAMBDA_DECAY_PER_HOUR: Final[float] = _env_float("AIOS_SKILL_LAMBDA_DECAY", 0.005)
SKILL_CONFIDENCE_BONUS_MAX: Final[float] = _env_float("AIOS_SKILL_BONUS_MAX", 0.2)
SKILL_REUSE_BOOST_MAX: Final[float] = _env_float("AIOS_SKILL_REUSE_BOOST_MAX", 0.15)
SKILL_REUSE_PENALTY_MAX: Final[float] = _env_float("AIOS_SKILL_REUSE_PENALTY_MAX", 0.60)
SKILL_REUSE_SUCCESS_K: Final[float] = _env_float("AIOS_SKILL_REUSE_SUCCESS_K", 3.0)
SKILL_REUSE_FAILURE_K: Final[float] = _env_float("AIOS_SKILL_REUSE_FAILURE_K", 1.5)
SKILL_REUSE_FACTOR_FLOOR: Final[float] = _env_float("AIOS_SKILL_REUSE_FLOOR", 0.25)
SKILL_REUSE_DEMOTE_NET_FAILURES: Final[int] = _env_int("AIOS_SKILL_REUSE_DEMOTE_NET", 3)

EARNED_AUTONOMY_ENABLED: Final[bool] = _env_bool("AIOS_EARNED_AUTONOMY", False)
EARNED_AUTONOMY_MIN_SUCCESSES: Final[int] = _env_int("AIOS_EARNED_AUTONOMY_MIN_SUCCESSES", 5)

SWARM_MAX_WORKERS: Final[int] = _env_int("AIOS_SWARM_MAX_WORKERS", 4)
SWARM_WORKER_CONCURRENCY: Final[int] = _env_int("AIOS_SWARM_WORKER_CONCURRENCY", 1)
SWARM_REDUNDANCY: Final[int] = _env_int("AIOS_SWARM_REDUNDANCY", 1)
SWARM_CLOUD_BURST_ENABLED: Final[bool] = _env_bool("AIOS_SWARM_CLOUD_BURST", False)
SWARM_WORKER_BACKEND: Final[str] = _env_str("AIOS_SWARM_WORKER_BACKEND", "auto")
SWARM_PHEROMONE_FIDELITY: Final[str] = _env_str("AIOS_SWARM_PHEROMONE_FIDELITY", "fast")
SWARM_CONFLICT_STRATEGY: Final[str] = _env_str("AIOS_SWARM_CONFLICT_STRATEGY", "merge")
SWARM_CONFLICT_TIMEOUT_S: Final[int] = _env_int("AIOS_SWARM_CONFLICT_TIMEOUT_S", 30)
SWARM_SCOUT_TEMPERATURE: Final[str] = _env_str(
    "AIOS_SWARM_SCOUT_TEMPERATURE", "adaptive:1.0:0.01:0.95"
)
SWARM_SCOUT_EXPLORATION_BONUS: Final[float] = _env_float(
    "AIOS_SWARM_SCOUT_EXPLORATION_BONUS", 1.414
)
SWARM_ADAPTIVE_SIZING: Final[bool] = _env_bool("AIOS_SWARM_ADAPTIVE_SIZING", True)
SWARM_MIN_WORKERS: Final[int] = _env_int("AIOS_SWARM_MIN_WORKERS", 1)
SWARM_MEMORY_PER_WORKER_MB: Final[int] = _env_int("AIOS_SWARM_MEMORY_PER_WORKER_MB", 256)

CONFIDENCE_THRESHOLD: Final[float] = _env_float("AIOS_CONFIDENCE_THRESHOLD", 0.72)
MAX_RED_ACTIONS_PER_SESSION: Final[int] = _env_int("AIOS_MAX_RED_ACTIONS", 3)
YELLOW_APPROVAL_TIMEOUT_MS: Final[int] = _env_int("AIOS_YELLOW_TIMEOUT_MS", 60_000)
RED_APPROVAL_TIMEOUT_MS: Final[int] = _env_int("AIOS_RED_TIMEOUT_MS", 30_000)

AUDIT_GENESIS_HASH: Final[str] = "0" * 64

INJECTION_VECTOR_SHIELD: Final[bool] = _env_bool("AIOS_INJECTION_VECTOR_SHIELD", False)
INJECTION_VECTOR_THRESHOLD: Final[float] = _env_float("AIOS_INJECTION_VECTOR_THRESHOLD", 0.6)

SCOPE_ROOTS: Final[tuple[Path, ...]] = _env_scope_roots(
    "AIOS_SCOPE_ROOTS", (PROJECT_ROOT / "training_ground",)
)

VERIFY_RUNNER: Final[str] = _env_str("AIOS_VERIFY_RUNNER", "python -m pytest")
APPROVED_EXECUTION_BACKEND: Final[str] = _env_str(
    "AIOS_APPROVED_EXECUTION_BACKEND", "host"
).strip().lower()
CONTAINER_RUNTIME: Final[str] = _env_str("AIOS_CONTAINER_RUNTIME", "docker")
CONTAINER_IMAGE: Final[str] = _env_str("AIOS_CONTAINER_IMAGE", "aios-executor:local")
CONTAINER_MEMORY_MB: Final[int] = _env_int("AIOS_CONTAINER_MEMORY_MB", 1024)
CONTAINER_CPUS: Final[float] = _env_float("AIOS_CONTAINER_CPUS", 1.0)
CONTAINER_PIDS_LIMIT: Final[int] = _env_int("AIOS_CONTAINER_PIDS_LIMIT", 128)
MAX_COMMAND_CHARS: Final[int] = _env_int("AIOS_MAX_COMMAND_CHARS", 8192)
MAX_COMMAND_OUTPUT_BYTES: Final[int] = _env_int("AIOS_MAX_COMMAND_OUTPUT_BYTES", 1_048_576)

OLLAMA_HOST: Final[str] = _env_str("OLLAMA_HOST", "http://127.0.0.1:11434")
LLM_MODEL: Final[str] = _env_str("AIOS_LLM_MODEL", "llama3.1:8b")
LLM_REQUEST_TIMEOUT_S: Final[int] = _env_int("AIOS_LLM_TIMEOUT_S", 120)
LLM_TEMPERATURE: Final[float] = _env_float("AIOS_LLM_TEMPERATURE", 0.1)
LLM_NUM_CTX: Final[int] = _env_int("AIOS_LLM_NUM_CTX", 4096)

INDEX_CHAT: Final[bool] = _env_bool("AIOS_INDEX_CHAT", True)
REFLECT_ON_FAILURE: Final[bool] = _env_bool("AIOS_REFLECT_ON_FAILURE", True)
INTERPRET_ALIGNMENT: Final[bool] = _env_bool("AIOS_INTERPRET_ALIGNMENT", True)

BEDROCK_REGION: Final[str] = _env_str("AIOS_BEDROCK_REGION", "")
BEDROCK_MODEL: Final[str] = _env_str("AIOS_BEDROCK_MODEL", "amazon.nova-lite-v1:0")
BEDROCK_MAX_TOKENS: Final[int] = _env_int("AIOS_BEDROCK_MAX_TOKENS", 1024)
BEDROCK_ENABLED: Final[bool] = bool(BEDROCK_REGION and BEDROCK_MODEL)

GEMINI_PROJECT: Final[str] = _env_str("AIOS_GEMINI_PROJECT", "")
GEMINI_LOCATION: Final[str] = _env_str("AIOS_GEMINI_LOCATION", "us-central1")
GEMINI_MODEL: Final[str] = _env_str("AIOS_GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_MAX_TOKENS: Final[int] = _env_int("AIOS_GEMINI_MAX_TOKENS", 1024)
GEMINI_THINKING_BUDGET: Final[int] = _env_int("AIOS_GEMINI_THINKING_BUDGET", 0)
GEMINI_ENABLED: Final[bool] = bool(GEMINI_PROJECT and GEMINI_MODEL)

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
ROUTER_PREFER_LOCAL: Final[bool] = _env_bool("AIOS_ROUTER_PREFER_LOCAL", True)
ROUTER_MAX_COST: Final[str] = _env_str("AIOS_ROUTER_MAX_COST", "high").strip().lower()
ROUTER_LLM_PICK: Final[bool] = _env_bool("AIOS_ROUTER_LLM_PICK", True)
ROUTER_CALIBRATION_WEIGHT: Final[float] = max(
    0.0, min(1.0, _env_float("AIOS_ROUTER_CALIBRATION_WEIGHT", 0.4))
)

API_HOST: Final[str] = _env_str("AIOS_API_HOST", "127.0.0.1")
API_PORT: Final[int] = _env_int("AIOS_API_PORT", 8000)
API_TOKEN: Final[str] = _env_str("AIOS_API_TOKEN", "")
TRUST_PROXY_HEADERS: Final[bool] = _env_bool("AIOS_TRUST_PROXY_HEADERS", False)
TRUSTED_PROXIES: Final[frozenset[str]] = frozenset(
    filter(None, _env_str("AIOS_TRUSTED_PROXIES", "").split(","))
)
ENABLE_DOCS: Final[bool] = _env_bool("AIOS_ENABLE_DOCS", False)
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
PROBE_BASE: Final[str] = _env_str("AIOS_PROBE_BASE", "http://127.0.0.1:8000")


def startup_banner() -> dict[str, object]:
    return {
        "host": API_HOST,
        "port": API_PORT,
        "token_set": bool(API_TOKEN),
        "token_length": len(API_TOKEN),
        "trust_proxy_headers": TRUST_PROXY_HEADERS,
        "trusted_proxies_configured": bool(TRUSTED_PROXIES),
        "docs_enabled": ENABLE_DOCS,
        "probe_base": PROBE_BASE,
        "router_cloud_tasks": list(ROUTER_CLOUD_TASKS),
        "earned_autonomy": EARNED_AUTONOMY_ENABLED,
        "council_runtime_dir": str(COUNCIL_RUNTIME_DIR),
        "scope_roots": [str(p) for p in SCOPE_ROOTS],
    }


__all__ = [
    "PROJECT_ROOT", "DATA_DIR", "MEMORY_DB_PATH", "APPROVAL_DB_PATH",
    "AUDIT_DB_PATH", "FAISS_INDEX_PATH", "ROLLBACK_DIR", "COUNCIL_RUNTIME_DIR",
    "EMBEDDING_MODEL", "EMBEDDING_DIM",
    "RETRIEVAL_ALPHA_BM25", "RETRIEVAL_BETA_FAISS", "RETRIEVAL_GAMMA_RECENCY",
    "RETRIEVAL_LAMBDA_DECAY_PER_HOUR",
    "MEMORY_COMPACT_UNVERIFIED_CHAT_DAYS", "MEMORY_COMPACT_EPISODIC_DAYS",
    "MEMORY_COMPACT_SEMANTIC_MAX_PER_TYPE", "MEMORY_COMPACT_WORKING_IDLE_MINUTES",
    "SKILL_LAMBDA_DECAY_PER_HOUR", "SKILL_CONFIDENCE_BONUS_MAX",
    "SKILL_REUSE_BOOST_MAX", "SKILL_REUSE_PENALTY_MAX",
    "SKILL_REUSE_SUCCESS_K", "SKILL_REUSE_FAILURE_K",
    "SKILL_REUSE_FACTOR_FLOOR", "SKILL_REUSE_DEMOTE_NET_FAILURES",
    "EARNED_AUTONOMY_ENABLED", "EARNED_AUTONOMY_MIN_SUCCESSES",
    "SWARM_MAX_WORKERS", "SWARM_WORKER_CONCURRENCY", "SWARM_REDUNDANCY",
    "SWARM_CLOUD_BURST_ENABLED",
    "SWARM_WORKER_BACKEND", "SWARM_PHEROMONE_FIDELITY",
    "SWARM_CONFLICT_STRATEGY", "SWARM_CONFLICT_TIMEOUT_S",
    "SWARM_SCOUT_TEMPERATURE", "SWARM_SCOUT_EXPLORATION_BONUS",
    "SWARM_ADAPTIVE_SIZING", "SWARM_MIN_WORKERS", "SWARM_MEMORY_PER_WORKER_MB",
    "CONFIDENCE_THRESHOLD", "MAX_RED_ACTIONS_PER_SESSION",
    "YELLOW_APPROVAL_TIMEOUT_MS", "RED_APPROVAL_TIMEOUT_MS",
    "AUDIT_GENESIS_HASH", "INJECTION_VECTOR_SHIELD", "INJECTION_VECTOR_THRESHOLD",
    "SCOPE_ROOTS", "VERIFY_RUNNER", "APPROVED_EXECUTION_BACKEND",
    "CONTAINER_RUNTIME", "CONTAINER_IMAGE", "CONTAINER_MEMORY_MB",
    "CONTAINER_CPUS", "CONTAINER_PIDS_LIMIT", "MAX_COMMAND_CHARS",
    "MAX_COMMAND_OUTPUT_BYTES", "OLLAMA_HOST", "LLM_MODEL",
    "LLM_REQUEST_TIMEOUT_S", "LLM_TEMPERATURE", "LLM_NUM_CTX",
    "INDEX_CHAT", "REFLECT_ON_FAILURE", "INTERPRET_ALIGNMENT",
    "BEDROCK_REGION", "BEDROCK_MODEL", "BEDROCK_MAX_TOKENS", "BEDROCK_ENABLED",
    "GEMINI_PROJECT", "GEMINI_LOCATION", "GEMINI_MODEL", "GEMINI_MAX_TOKENS",
    "GEMINI_THINKING_BUDGET", "GEMINI_ENABLED",
    "ROUTER_CLOUD_TASKS", "ROUTER_PREFER_LOCAL", "ROUTER_MAX_COST",
    "ROUTER_LLM_PICK", "ROUTER_CALIBRATION_WEIGHT",
    "API_HOST", "API_PORT", "API_TOKEN", "TRUST_PROXY_HEADERS",
    "TRUSTED_PROXIES", "ENABLE_DOCS", "API_CORS_ORIGINS", "PROBE_BASE",
    "startup_banner",
]
