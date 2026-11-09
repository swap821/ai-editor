"""One registry of brains (2026-11-04, the consistency register's provider rows).

Which brains exist, which are cloud, what they cost and which client serves
each are written once, in :data:`aios.core.router.PROVIDERS`. On 2026-11-04,
before it, five layers kept their own shorter lists without the operator's
plans, the hiring broker priced openai differently from the router, and a turn
Vertex served was recorded as ``ollama`` because the two directions of "name
to client" were separate ladders. This pins:

* no hand-written list of provider names outside the registry, except the
  named fixtures that are lists on purpose;
* every layer agrees which brains are cloud, what each costs and what it is
  for, because each reads the registry;
* a brain's name and its client round-trip, for every brain, and an explicit
  model id with its prefix reaches its client;
* a brain added to the registry without a client mapping fails loudly.
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios.core import failover, router, router_wiring
from aios.domain.intelligence import broker as broker_module
from aios.domain.intelligence.privacy import LOCAL_PROVIDERS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import consistency_audit  # noqa: E402

#: The hand-written provider lists that stay, each for its reason. A new list
#: anywhere, or a second one in these files, fails.
ALLOWED_LISTS: dict[str, tuple[int, str]] = {
    "aios/application/governance/adversarial_simulations.py": (
        1,
        "organ 46's privacy probe asks about a fixed set of candidates",
    ),
    "aios/application/governance/r15_runtime_proof.py": (
        2,
        "the R15 proof's scenarios name fixed candidates",
    ),
    "aios/application/turns/generate_pipeline.py": (
        1,
        "a state bag keyed by variable names; its cloud picks are the "
        "side-job-cloud-brain row, which the one engine for workers takes on",
    ),
    "tools/model_call_inventory.py": (
        1,
        "the inventory counts calls for the two servers it instruments",
    ),
}


def test_no_hand_written_provider_list_outside_the_registry() -> None:
    found = Counter(
        site.rpartition(":")[0] for site in consistency_audit.provider_lists()
    )
    allowed = {path: count for path, (count, _why) in ALLOWED_LISTS.items()}
    assert dict(found) == allowed, (
        "a hand-written list of provider names appeared or went away; derive it "
        "from aios.core.router.PROVIDERS, or name it here with its reason: "
        f"found {dict(found)}"
    )


@pytest.mark.parametrize("spec", router.PROVIDERS, ids=lambda s: s.name)
def test_every_layer_agrees_whether_a_brain_is_cloud(spec: router.ProviderSpec) -> None:
    assert failover._is_cloud_provider(spec.name) is spec.is_cloud
    assert failover._is_local_provider(spec.name) is (not spec.is_cloud)
    assert (spec.name in LOCAL_PROVIDERS) is (not spec.is_cloud)
    assert (spec.name in router.CLOUD_PROVIDER_NAMES) is spec.is_cloud


class _Cloud:
    model = "m"

    def __init__(self, name: str) -> None:
        self.name = name

    def list_models(self) -> dict:
        return {"models": ["qwen2.5-coder:7b"]}

    def models(self) -> tuple[str, ...]:
        return ("claude-sonnet-5-5",)


def _clients() -> dict[str, object]:
    return {name: _Cloud(name) for name in router.PROVIDER_NAMES}


def _rows(monkeypatch) -> list[router.Provider]:
    monkeypatch.setattr(
        router_wiring, "catalog_models", lambda client, name, default: (default,)
    )
    c = _clients()
    return router_wiring._build_providers(
        c["ollama"],
        c["bedrock"],
        c["gemini"],
        openai=c["openai"],
        anthropic=c["anthropic"],
        vertex_maas=c["vertexmaas"],
        plan=c["plan"],
    )


def test_the_routers_rows_are_the_registrys(monkeypatch) -> None:
    rows = _rows(monkeypatch)
    assert {r.name for r in rows} == set(router.PROVIDER_NAMES), (
        "every brain is offered"
    )
    for row in rows:
        spec = router.provider_spec(row.name)
        assert (row.privacy, row.cost) == (spec.privacy, spec.cost), row.name


def test_the_hiring_broker_prices_and_skills_are_the_registrys() -> None:
    broker = broker_module.HiringBroker()
    for spec in router.PROVIDERS:
        assert broker._provider_costs[spec.name] == spec.cost, spec.name
        assert broker._provider_capabilities[spec.name] == list(spec.skills), spec.name


@pytest.mark.parametrize("name", router.PROVIDER_NAMES)
def test_a_brains_name_and_its_client_round_trip(name: str, monkeypatch) -> None:
    c = _clients()
    monkeypatch.setattr(router_wiring, "_plan_client", lambda: c["plan"])
    kwargs = dict(
        openai=c["openai"], anthropic=c["anthropic"], vertex_maas=c["vertexmaas"]
    )
    client = router_wiring._client_for(
        name, c["ollama"], c["bedrock"], c["gemini"], **kwargs
    )
    assert client is c[name]
    assert (
        router_wiring._provider_name(client, c["bedrock"], c["gemini"], **kwargs)
        == name
    )
    assert router_wiring._active_route(
        client, c["bedrock"], c["gemini"], "m", **kwargs
    ) == (
        name,
        "m",
    )


@pytest.mark.parametrize("spec", router.cloud_providers(), ids=lambda s: s.name)
def test_an_explicit_model_id_reaches_its_brain(
    spec: router.ProviderSpec, monkeypatch
) -> None:
    c = _clients()
    monkeypatch.setattr(router_wiring, "_plan_client", lambda: c["plan"])
    model = "claude-sonnet-5-5" if spec.name == router.PROVIDER_PLAN else "some-model"
    model_id = model if spec.name == router.PROVIDER_BEDROCK else spec.prefix + model
    client, served = router_wiring._select_chat_client(
        model_id,
        c["ollama"],
        c["bedrock"],
        gemini=c["gemini"],
        openai=c["openai"],
        anthropic=c["anthropic"],
        vertex_maas=c["vertexmaas"],
    )
    assert (client, served) == (c[spec.name], model)


def test_every_list_of_brains_is_the_registry() -> None:
    from aios.application.read_models.governance_projections import KNOWN_PROVIDER_NAMES

    assert KNOWN_PROVIDER_NAMES == router.PROVIDER_NAMES
    assert (
        tuple(router_wiring.clients_by_provider(None, plan=None))
        == router.PROVIDER_NAMES
    )
    assert (
        set(router._PREFIX)
        == set(router._DEFAULT_CAPABILITY)
        == set(router.PROVIDER_NAMES)
    )


def test_a_brain_the_wiring_does_not_know_fails_loudly(monkeypatch) -> None:
    monkeypatch.setattr(router, "PROVIDER_NAMES", (*router.PROVIDER_NAMES, "newbrain"))
    with pytest.raises(KeyError):
        router_wiring.clients_by_provider(None, plan=None)


def test_the_readiness_probe_names_every_configured_cloud_brain(monkeypatch) -> None:
    from aios.api.routes import system

    for spec in router.cloud_providers():
        monkeypatch.setattr(system.config, spec.enabled_setting, True, raising=False)
    ollama = SimpleNamespace(list_models=lambda: {"available": False, "models": []})
    _ok, report = system._check_providers(ollama)
    assert report["cloud_configured"] == sorted(router.CLOUD_PROVIDER_NAMES)


def test_a_side_job_takes_the_first_configured_unrefused_cloud_brain() -> None:
    from aios.core import model_availability

    clients = {"bedrock": _Cloud("bedrock"), "plan": _Cloud("plan")}
    assert router_wiring.first_cloud_brain(clients)[0] == "bedrock", "registry order"
    model_availability.mark_unavailable("bedrock", "m")
    try:
        assert router_wiring.first_cloud_brain(clients)[0] == "plan", (
            "a refused model is passed over"
        )
    finally:
        model_availability.clear()
    assert router_wiring.first_cloud_brain({"ollama": _Cloud("ollama")}) is None, (
        "never local"
    )


def _hand_picks(path: Path) -> list[int]:
    """Lines where a cloud client is picked by hand: ``gemini or bedrock``."""
    names = {
        "gemini",
        "bedrock",
        "openai",
        "anthropic",
        "openai_client",
        "anthropic_client",
    }
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            picked = {
                v.id if isinstance(v, ast.Name) else getattr(v, "attr", None)
                for v in node.values
            }
            if len(picked & names) >= 2:
                found.append(node.lineno)
    return found


def test_every_side_job_takes_its_cloud_brain_one_way() -> None:
    """The council's dissent, CRAG's cloud source and the swarm's cloud burst
    each picked their own cloud brain until 2026-11-09."""
    picks = {
        p.relative_to(ROOT).as_posix(): lines
        for p in (ROOT / "aios").rglob("*.py")
        if (lines := _hand_picks(p))
    }
    assert not picks, f"a cloud brain picked by hand: {picks}"
    for rel in (
        "aios/council/gateway_reasoning.py",
        "aios/api/routes/chat.py",
        "aios/application/turns/generate_pipeline.py",
    ):
        source = (ROOT / rel).read_text(encoding="utf-8")
        assert "first_cloud_brain(" in source or "side_job_cloud(" in source, rel


#: The wiring functions that take each brain's client by keyword.
_CLIENT_TAKERS = {
    "_active_route",
    "_provider_name",
    "_client_for",
    "_build_providers",
    "_select_chat_client",
    "clients_by_provider",
    "side_job_cloud",
}


def test_a_call_that_names_one_brains_client_names_them_all() -> None:
    """On 2026-11-09 three of five calls in the generate pipeline passed every
    client but Vertex's: a turn Vertex served was named ollama, and one of
    them set the turn's privacy target, so its context was compiled for a
    LOCAL brain. A production call that hands over one cloud client by
    keyword hands over all of them."""
    missing = []
    for path in (ROOT / "aios").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in _CLIENT_TAKERS:
                continue
            given = {k.arg for k in node.keywords}
            if "openai" in given and not {"anthropic", "vertex_maas"} <= given:
                rel = path.relative_to(ROOT).as_posix()
                missing.append(
                    f"{rel}:{node.lineno} {name} lacks {sorted({'anthropic', 'vertex_maas'} - given)}"
                )
    assert not missing, "\n".join(missing)
