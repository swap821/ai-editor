"""``python -m aios clerk``: the operator's controls for the local clerk.

The clerk had never done a job on the operator's machine (2026-10-11): no
model was admitted, and there was no way to admit one except raw HTTP routes
with no screen. This is the way, on the same service those routes use.

* ``status``   models, their roles, and which jobs each may take. Read-only.
* ``refresh``  reconcile the registry with what Ollama has installed.
* ``approve``  the Human Sovereign's admission decision -- HIS act: it needs
               his own terminal and the model id typed back.
* ``qualify``  run the qualification suite (a measurement; needs approval).
* ``grant``    give a model roles its qualification evidence backs -- HIS act.
* ``revoke``   withdraw approval. The safe direction, so never gated.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Sequence, TextIO


class ClerkAdminError(RuntimeError):
    """A refusal the operator should read."""


def default_service() -> Any:
    """The same LocalWorkforceService the API routes use, on this data dir."""
    from aios.api.deps import (
        get_emergency_stop,
        get_local_workforce_registry,
        get_local_workforce_service,
        get_ollama_client,
    )

    # Providers come from the dependency module, the one place allowed to
    # construct them (tests/architecture/test_intelligence_boundary.py).
    ollama = get_ollama_client()
    registry = get_local_workforce_registry(ollama)
    return get_local_workforce_service(registry, ollama, get_emergency_stop())


def default_registry() -> Any:
    """The registry alone: a read never builds the service, whose provenance
    store would be created on this data dir as a side effect."""
    from aios.api.deps import get_local_workforce_registry, get_ollama_client

    return get_local_workforce_registry(get_ollama_client())


def eligible_roles(models: Sequence[Any]) -> dict[str, list[str]]:
    """Which roles each model may take, asked exactly as the dispatcher asks."""
    from aios.domain.local_workforce.contracts import (
        LocalClerkRuntimeAuthority,
        LocalJobProfile,
        LocalJobRequest,
    )

    authority = LocalClerkRuntimeAuthority()
    deadline = datetime.now(timezone.utc) + timedelta(seconds=10)
    roles: dict[str, list[str]] = {}
    for profile in LocalJobProfile:
        request = LocalJobRequest(
            job_id="clerk-admin-probe",
            job_profile=profile,
            input_schema_version="1.0",
            evidence_references=frozenset(),
            redacted_payload="",
            token_budget=1,
            deadline=deadline,
            required_output_schema={},
        )
        for model in authority.eligible_models(request, list(models)):
            roles.setdefault(model.model_id, []).append(profile.value)
    return roles


def _confirm(
    model_id: str, verb: str, stdin: TextIO, ask: Callable[[str], str]
) -> None:
    """The operator's act: his own terminal, the model id typed back."""
    if not stdin.isatty():
        raise ClerkAdminError(
            f"`clerk {verb}` is the operator's decision: run it in your own terminal"
        )
    typed = ask(f"Type {model_id} to {verb} it: ").strip()
    if typed != model_id:
        raise ClerkAdminError(f"typed {typed!r}, not {model_id!r}: nothing changed")


def run(
    command: str,
    *,
    model_id: Optional[str] = None,
    roles: Sequence[str] = (),
    service: Any = None,
    stdin: TextIO = sys.stdin,
    ask: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
) -> int:
    if command == "status":
        registry = service.registry if service is not None else default_registry()
        models = list(registry.list_models())
        eligible = eligible_roles(models)
        for model in models:
            out(
                f"  {model.model_id:<26} approved={'yes' if model.operator_approved else 'no ':<3} "
                f"admission={model.admission_status:<9} health={model.health:<8} "
                f"may take: {', '.join(eligible.get(model.model_id, [])) or 'nothing'}"
            )
        out(f"{len(eligible)} of {len(models)} models may take a job")
        return 0 if eligible else 1
    service = service if service is not None else default_service()
    if command == "refresh":
        out(f"{len(service.refresh())} models registered")
        return 0
    if model_id is None:
        raise ClerkAdminError(f"`clerk {command}` needs a model id")
    if command == "approve":
        _confirm(model_id, "approve", stdin, ask)
        service.approve(model_id, True)
        out(f"approved {model_id}; next: `python -m aios clerk qualify {model_id}`")
        return 0
    if command == "revoke":
        service.approve(model_id, False)
        out(f"approval withdrawn: {model_id}")
        return 0
    if command == "qualify":
        result = service.qualify(model_id)
        out(f"{model_id}: {result.get('status')}")
        tests = (result.get("qualification") or {}).get("test_results") or ()
        for test in tests:
            if not test.get("passed"):
                out(
                    f"  failed {test.get('test_id')}: {test.get('detail') or test.get('reason') or ''}"
                )
        if result.get("reason"):
            out(f"  reason: {result['reason']}")
        return 0 if result.get("status") == "admitted" else 1
    if command == "grant":
        if not roles:
            raise ClerkAdminError("`clerk grant` needs at least one role")
        _confirm(model_id, "grant roles to", stdin, ask)
        model = service.update_profiles(model_id, list(roles))
        out(
            f"{model_id} may now take: {', '.join(sorted(p.value for p in model.allowed_job_profiles))}"
        )
        return 0
    raise ClerkAdminError(f"unknown clerk command {command!r}")


__all__ = [
    "ClerkAdminError",
    "default_registry",
    "default_service",
    "eligible_roles",
    "run",
]
