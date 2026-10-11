"""Production keys reach production -- from the OS store, never from a file.

Found 2026-10-11 by measuring (docs/PRODUCTION_HARDENING.md): the production
container was never given its verification key, its learning key or any cloud
key, and dialled 127.0.0.1 for Ollama -- itself. Pinned here:

* production refuses to start without every required key, or with the
  learning key's public half unpinned;
* secrets are never read from ``.env`` (AGENTS.md §VII.4);
* the stored keys reach Compose in memory; an explicit volatile env var wins;
* ``gagos keys`` never prints a value, and ``set`` needs the operator's own
  terminal;
* the compose file hands the container its keys, the host's Ollama and the
  pinned public keys.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios import launcher
from aios.operations import keystore as ks

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(monkeypatch) -> ks.MemoryKeystore:
    memory = ks.MemoryKeystore()
    monkeypatch.setattr(launcher, "_keystore", lambda: memory)
    for name in ks.NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("AIOS_APPROVED_EXECUTION_BACKEND", raising=False)
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "/usr/bin/docker")
    return memory


def _config(tmp_path: Path, profile: str = "production") -> launcher.LauncherConfig:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    return launcher.LauncherConfig(
        repo_root=repo,
        data_dir=tmp_path / "data",
        profile=profile,
        api_port=8000,
        gateway_port=3000,
        compose_file=repo / "docker-compose.yml",
        state_file=tmp_path / "data" / "launcher-state.json",
        log_file=tmp_path / "data" / "launcher.log",
    )


def _keys(config, args: list[str]) -> int:
    parsed = SimpleNamespace(
        keys_command=args[0], names=args[1:], missing=False, rotate=False
    )
    if args[0] == "generate" and args[1:] == ["--missing"]:
        parsed.names, parsed.missing = [], True
    if args[0] in {"set", "delete"}:
        parsed.name = args[1]
    return launcher.keys_command(config, parsed)


def test_production_refuses_without_the_verification_and_learning_keys(
    store, tmp_path
) -> None:
    config = _config(tmp_path)
    for name in (
        "AIOS_API_TOKEN",
        "AIOS_EXECUTOR_TOKEN",
        "AIOS_GRAFANA_ADMIN_PASSWORD",
    ):
        store.set(name, "x" * 40)
    with pytest.raises(launcher.LauncherError) as refused:
        launcher._production_preflight(config)
    assert "AIOS_VERIFICATION_AUTHORITY_KEY" in str(refused.value)
    assert "AIOS_LEARNING_KEY_LIVE" in str(refused.value)


def test_secrets_in_dotenv_are_never_read(store, tmp_path) -> None:
    config = _config(tmp_path)
    (config.repo_root / ".env").write_text(
        "\n".join(f"{name}={'y' * 40}" for name in ks.REQUIRED), encoding="utf-8"
    )
    with pytest.raises(launcher.LauncherError, match="configure non-default"):
        launcher._production_preflight(config)


def test_an_unpinned_learning_key_refuses_and_a_pinned_one_starts(
    store, tmp_path, capsys
) -> None:
    config = _config(tmp_path)
    assert _keys(config, ["generate", "--missing"]) == 0
    with pytest.raises(launcher.LauncherError, match="not pinned"):
        launcher._production_preflight(config)
    assert _keys(config, ["pin"]) == 0
    assert _keys(config, ["pin"]) == 0, "pinning twice is idempotent"
    pins = json.loads((config.repo_root / launcher._LEARNING_PINS).read_text())
    assert len(pins["keys"]["live"]) == 1
    launcher._production_preflight(config)  # every key stored and the key pinned


def test_the_stored_keys_reach_compose_in_memory(store, tmp_path, monkeypatch) -> None:
    store.set("AIOS_VERIFICATION_AUTHORITY_KEY", "from-the-store")
    store.set("GEMINI_API_KEY", "g")
    env = launcher._child_environment(_config(tmp_path))
    assert env["AIOS_VERIFICATION_AUTHORITY_KEY"] == "from-the-store"
    assert env["GEMINI_API_KEY"] == "g"
    assert env["AIOS_HOST_DATA_DIR"] == str(tmp_path / "data")
    monkeypatch.setenv("AIOS_VERIFICATION_AUTHORITY_KEY", "explicit")
    assert (
        launcher._child_environment(_config(tmp_path))[
            "AIOS_VERIFICATION_AUTHORITY_KEY"
        ]
        == "explicit"
    )
    dev = launcher._child_environment(_config(tmp_path, profile="development"))
    assert "GEMINI_API_KEY" not in dev, "only production receives the stored keys"


def test_keys_status_never_prints_a_value(store, tmp_path, capsys) -> None:
    config = _config(tmp_path)
    store.set("AIOS_API_TOKEN", "visible-if-leaked")
    assert _keys(config, ["status"]) == 1
    _keys(config, ["generate", "--missing"])
    _keys(config, ["pin"])
    assert _keys(config, ["status"]) == 0
    out = capsys.readouterr().out
    assert "visible-if-leaked" not in out
    for name in ks.REQUIRED:
        value = store.get(name)
        assert value and value not in out, f"{name}'s value was printed"


def test_generate_missing_then_nothing_left(store, tmp_path, capsys) -> None:
    config = _config(tmp_path)
    _keys(config, ["generate", "--missing"])
    assert all(store.get(name) for name in ks.REQUIRED)
    capsys.readouterr()
    _keys(config, ["generate", "--missing"])
    assert "nothing to generate" in capsys.readouterr().out


def test_generate_never_overwrites_without_rotate(store, tmp_path) -> None:
    store.set("AIOS_API_TOKEN", "kept")
    with pytest.raises(launcher.LauncherError, match="already stored"):
        _keys(_config(tmp_path), ["generate", "AIOS_API_TOKEN"])
    assert store.get("AIOS_API_TOKEN") == "kept"


def test_set_needs_the_operators_own_terminal(store, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(launcher.sys, "stdin", io.StringIO("piped-value\n"))
    with pytest.raises(launcher.LauncherError, match="your own terminal"):
        _keys(_config(tmp_path), ["set", "AWS_BEARER_TOKEN_BEDROCK"])
    assert store.get("AWS_BEARER_TOKEN_BEDROCK") is None


def test_no_store_is_said_plainly(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(launcher, "_keystore", lambda: None)
    with pytest.raises(launcher.LauncherError, match="no OS credential store"):
        _keys(_config(tmp_path), ["status"])


# --------------------------------------------------------------------------- #
# The compose file itself
# --------------------------------------------------------------------------- #


def _aios_service() -> dict:
    import yaml

    return yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))[
        "services"
    ]["aios"]


def _env_names(service: dict) -> dict[str, str]:
    return {
        item.partition("=")[0]: item.partition("=")[2]
        for item in service["environment"]
    }


def test_the_container_dials_the_hosts_ollama_not_itself() -> None:
    env = _env_names(_aios_service())
    host = env.get("OLLAMA_HOST", "")
    assert host and "host.docker.internal" in host
    assert not any(lo in host for lo in ("127.0.0.1", "localhost"))
    assert "host.docker.internal:host-gateway" in _aios_service().get("extra_hosts", [])


def test_the_container_is_handed_every_production_key() -> None:
    env = _env_names(_aios_service())
    for name in ks.NAMES:
        if name in {
            "AIOS_API_TOKEN",
            "AIOS_EXECUTOR_TOKEN",
            "AIOS_GRAFANA_ADMIN_PASSWORD",
        }:
            continue  # wired before this change, by interpolation
        assert name in env, f"the production container is never given {name}"


def test_the_container_sees_the_pinned_keys_and_the_launchers_data_dir() -> None:
    volumes = _aios_service()["volumes"]
    assert any(
        "LEARNING_PUBLIC_KEYS.json:/app/.aios/state/LEARNING_PUBLIC_KEYS.json:ro" in v
        for v in volumes
    )
    assert any(
        v.startswith("${AIOS_HOST_DATA_DIR") and v.endswith(":/app/data")
        for v in volumes
    )


def test_volatile_env_vars_still_satisfy_production(
    store, tmp_path, monkeypatch
) -> None:
    """Off Windows -- CI, Linux -- keys can only be volatile env vars, and an
    explicit one always wins over the store."""
    config = _config(tmp_path)
    seed = ks.GENERATORS["AIOS_LEARNING_KEY_LIVE"]()
    for name in ks.REQUIRED:
        value = seed if name == "AIOS_LEARNING_KEY_LIVE" else ks.GENERATORS[name]()
        monkeypatch.setenv(name, value)
    pins = config.repo_root / launcher._LEARNING_PINS
    pins.parent.mkdir(parents=True)
    pins.write_text(json.dumps({"keys": {"live": [ks.learning_public_key(seed)]}}))
    launcher._production_preflight(config)  # the store is empty: env alone suffices


def test_production_gets_an_executor_workspace_unless_one_is_set(
    store, tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("AIOS_EXECUTOR_HOST_WORKSPACE_ROOT", raising=False)
    env = launcher._child_environment(_config(tmp_path))
    assert env["AIOS_EXECUTOR_HOST_WORKSPACE_ROOT"] == str(
        tmp_path / "data" / "executor-jobs"
    )
    monkeypatch.setenv("AIOS_EXECUTOR_HOST_WORKSPACE_ROOT", "D:/jobs")
    assert (
        launcher._child_environment(_config(tmp_path))[
            "AIOS_EXECUTOR_HOST_WORKSPACE_ROOT"
        ]
        == "D:/jobs"
    )
