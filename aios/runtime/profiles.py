"""Runtime profiles -- system-level operating modes for the AI-OS process.

A ``RuntimeProfile`` is *not* a caste profile. It describes the runtime
environment the whole process operates in: where execution may run, which
task classes may leave the machine, whether autonomy can be earned, and
which experimental subsystems are enabled. The active profile is loaded by
``PolicyKernel`` and drives profile-scoped decisions across the backend.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from aios import config

ExecutionBackend = Literal["host", "container"]
ResourceMode = Literal["lean", "balanced", "performance"]


@dataclass(frozen=True)
class RuntimeProfile:
    """A system-level operating-mode profile."""

    name: str
    description: str
    execution_backend: ExecutionBackend
    earned_autonomy: bool
    router_cloud_tasks: tuple[str, ...]
    router_prefer_local: bool
    router_max_cost: str
    swarm_cloud_burst: bool
    offline_mode: bool
    resource_mode: ResourceMode
    plan_stage: bool
    narrative_self: bool
    facts_auto_extract: bool
    pheromone_enabled: bool
    queen_enabled: bool
    live_surface: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict."""
        data = asdict(self)
        data["router_cloud_tasks"] = list(data["router_cloud_tasks"])
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeProfile":
        """Build a profile from a dict, normalising types."""
        cloud_tasks = data.get("router_cloud_tasks", [])
        if isinstance(cloud_tasks, str):
            cloud_tasks = [t.strip() for t in cloud_tasks.split(",") if t.strip()]
        backend = str(data.get("execution_backend", "host")).lower()
        resource = str(data.get("resource_mode", "balanced")).lower()
        return cls(
            name=str(data["name"]).lower(),
            description=str(data.get("description", "")),
            execution_backend=backend,  # type: ignore[arg-type]
            earned_autonomy=bool(data.get("earned_autonomy", False)),
            router_cloud_tasks=tuple(str(t).strip().lower() for t in cloud_tasks),
            router_prefer_local=bool(data.get("router_prefer_local", True)),
            router_max_cost=str(data.get("router_max_cost", "high")).lower(),
            swarm_cloud_burst=bool(data.get("swarm_cloud_burst", False)),
            offline_mode=bool(data.get("offline_mode", False)),
            resource_mode=resource,  # type: ignore[arg-type]
            plan_stage=bool(data.get("plan_stage", True)),
            narrative_self=bool(data.get("narrative_self", False)),
            facts_auto_extract=bool(data.get("facts_auto_extract", True)),
            pheromone_enabled=bool(data.get("pheromone_enabled", False)),
            queen_enabled=bool(data.get("queen_enabled", False)),
            live_surface=bool(data.get("live_surface", False)),
        )

    def cloud_task_allowed(self, task: str) -> bool:
        """Return True if *task* may be routed to a cloud provider."""
        return task.strip().lower() in self.router_cloud_tasks


BUILTIN_REGISTRY_PATH: Path = Path(__file__).resolve().parent / "profiles.json"
RUNTIME_PROFILES_DIR: Path = config.DATA_DIR / "runtime_profiles"
RUNTIME_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
ACTIVE_PROFILE_PATH: Path = RUNTIME_PROFILES_DIR / "active.json"


def load_builtin_profiles(path: Path | None = None) -> dict[str, RuntimeProfile]:
    """Load the built-in profile registry from ``profiles.json``."""
    registry_path = path or BUILTIN_REGISTRY_PATH
    with registry_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return {
        str(name).lower(): RuntimeProfile.from_dict(profile)
        for name, profile in raw.items()
    }


#: Built-in profiles shipped with the process. Loaded once at import time so
#: the kernel can resolve names without touching disk on every decision.
RUNTIME_PROFILES: dict[str, RuntimeProfile] = load_builtin_profiles()


def default_profile_name() -> str:
    """Return the default built-in profile name."""
    return "local-first"


def get_profile(name: str) -> RuntimeProfile | None:
    """Look up a profile by name, returning ``None`` for unknown names."""
    return RUNTIME_PROFILES.get(name.strip().lower())


def list_profile_names() -> list[str]:
    """Return the names of all known built-in profiles, sorted."""
    return sorted(RUNTIME_PROFILES.keys())


def save_active_profile(profile: RuntimeProfile, path: Path | None = None) -> None:
    """Persist *profile* as the active profile on disk."""
    target = path or ACTIVE_PROFILE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": profile.name,
        "source": "runtime_profiles.active.json",
        "profile": profile.to_dict(),
    }
    with target.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def load_active_profile_name(path: Path | None = None) -> str | None:
    """Return the name persisted as active, if any."""
    target = path or ACTIVE_PROFILE_PATH
    if not target.exists():
        return None
    try:
        with target.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return str(payload.get("name", "")).strip().lower() or None
    except (json.JSONDecodeError, OSError):
        return None


__all__ = [
    "ACTIVE_PROFILE_PATH",
    "BUILTIN_REGISTRY_PATH",
    "RUNTIME_PROFILES",
    "RUNTIME_PROFILES_DIR",
    "ExecutionBackend",
    "ResourceMode",
    "RuntimeProfile",
    "default_profile_name",
    "get_profile",
    "list_profile_names",
    "load_active_profile_name",
    "load_builtin_profiles",
    "save_active_profile",
]
