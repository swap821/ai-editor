"""Universal pre-dispatch ActionEnvelope -> PolicyKernel -> ActionBroker gate.

The command/approval surfaces have route-specific capability flows because
they stream or resume work.  Ordinary API mutations use this dependency as a
single, boring boundary: request identity and the exact JSON body are bound
before the route handler is allowed to run.  YELLOW routes return an opaque
capability on the first request and consume it only when the caller explicitly
retries with ``X-AIOS-Capability``.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from aios.api.deps import get_action_broker, get_emergency_stop, get_identity_service
from aios.application.action_broker import ActionBroker, PolicyBrokerError
from aios.application.governance import EmergencyStopError
from aios.application.identity.service import IdentityService
from aios.domain.actions.envelope import (
    ActionEnvelope,
    ActionType,
    Principal as EnvelopePrincipal,
)
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.proof import ConsumedCapabilityProof
from aios.domain.identity.models import Principal
from aios.policy.kernel import _route_match


CAPABILITY_HEADER = "x-aios-capability"

# These routes already construct their own complete envelope and capability
# binding because they have a bespoke streaming/resume or rollback protocol.
# They remain in the conformance set; the dependency simply must not consume a
# token before the route-specific flow does.
_EXACT_BROKER_ROUTE_KEYS = frozenset(
    {
        "/api/v1/execute",
        "/api/terminal",
        "/api/v1/approval/req",
        "/api/v1/rollback",
        "/api/v1/self-analysis/proposals/{proposal_id}/apply",
        "/api/v1/council/missions/{mission_id}/rollback",
        "/api/generate",
    }
)

_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_EMERGENCY_CLEAR_ROUTE = "/api/v1/governance/emergency-stop/clear"


@dataclass(frozen=True)
class ActionGuardResult:
    """The broker result retained on ``request.state`` for observability."""

    envelope: ActionEnvelope
    decision: Any
    capability_digest: str | None = None


def _is_exact_broker_route(path: str) -> bool:
    return any(_route_match(route, path) for route in _EXACT_BROKER_ROUTE_KEYS)


async def _request_payload(request: Request) -> dict[str, Any]:
    """Read a stable object payload without leaking raw non-JSON request data."""
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("multipart/form-data"):
        try:
            form = await request.form()
        except RuntimeError as exc:
            raise HTTPException(
                status_code=400,
                detail="multipart request body is unavailable for action binding",
            ) from exc
        payload: dict[str, Any] = {}
        for key, value in form.multi_items():
            if hasattr(value, "filename") and hasattr(value, "read"):
                position = value.file.tell()
                raw = await value.read()
                await value.seek(position)
                payload[key] = {
                    "filename": value.filename,
                    "content_type": value.content_type,
                    "size": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            else:
                payload[key] = value
        return payload
    body = await request.body()
    if not body:
        return {}
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"raw_body_sha256": hashlib.sha256(body).hexdigest()}
    if isinstance(value, dict):
        return value
    return {"body": value}


def _validate_json_body_against_route(
    request: Request, payload: dict[str, Any]
) -> None:
    """Preserve FastAPI's normal 422 boundary before issuing a capability.

    Router dependencies run before the endpoint's body model is handed to the
    function.  Reuse FastAPI's own compiled body field here so malformed input
    cannot mint an approval token and validation errors retain their normal
    response contract.  Multipart/raw routes intentionally stay on their
    digest-only path.
    """
    content_type = request.headers.get("content-type", "").lower()
    if not content_type.startswith("application/json"):
        return
    route = request.scope.get("route")
    body_params = getattr(getattr(route, "dependant", None), "body_params", ())
    if len(body_params) != 1:
        return
    _value, errors = body_params[0].validate(payload, {}, loc=("body",))
    if errors:
        raise RequestValidationError(errors)


def _resource_for(
    path: str, path_params: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    target_keys = (
        "path",
        "filepath",
        "filePath",
        "source_id",
        "sourceId",
        "mission_id",
        "missionId",
        "proposal_id",
        "proposalId",
        "snapshot_id",
        "snapshotId",
        "worker_id",
        "workerId",
    )
    target = next(
        (payload.get(key) for key in target_keys if payload.get(key) is not None), None
    )
    return {
        "route": path,
        "path_params": dict(path_params),
        "target": target,
    }


def _binding_for(envelope: ActionEnvelope, principal: Principal) -> CapabilityBinding:
    return CapabilityBinding(
        operator_id=principal.principal_id,
        device_id=principal.device_id,
        authentication_event_id=principal.authentication_event_id,
        session_id=principal.session_id,
        action_type=envelope.action_type.value,
        route=envelope.route,
        http_method=envelope.http_method,
        payload_digest=envelope.payload_digest or "",
        resource_digest=envelope.resource_digest or "",
        mission_id=envelope.mission_id,
        contract_digest=envelope.contract_digest,
        policy_version=envelope.policy_version,
        scope=f"route:{envelope.route}",
        verification_requirement="route_policy_v1",
    )


async def enforce_action_boundary(
    request: Request,
    broker: ActionBroker = Depends(get_action_broker),
    identity: IdentityService = Depends(get_identity_service),
) -> ActionGuardResult | None:
    """Authorize every ordinary mutation before its route body executes."""
    if request.method.upper() not in _MUTATION_METHODS:
        return None
    path = request.url.path
    if _is_exact_broker_route(path):
        return None

    authority = broker.kernel.route_authority(path, request.method)
    if authority.action_type is ActionType.UNKNOWN:
        raise HTTPException(
            status_code=403, detail="unknown mutation route blocked by policy"
        )

    raw_cookie = request.cookies.get("session_id")
    principal = identity.get_authenticated_principal(raw_cookie) if raw_cookie else None
    # ``session`` is the local conversation/session boundary, not the
    # Human-Sovereign identity boundary.  Chat and the other GREEN session
    # routes deliberately remain usable with the legacy conversation cookie
    # (or a body session fallback handled by the route itself).  Only
    # ``server-session`` routes require the durable operator principal.
    if authority.actor_source == "server-session" and principal is None:
        raise HTTPException(
            status_code=401, detail="authenticated operator session required"
        )
    if authority.authority_class == "YELLOW":
        if principal is None:
            raise HTTPException(
                status_code=401, detail="authenticated operator session required"
            )
        if principal.authentication_level != "privileged":
            raise HTTPException(
                status_code=403,
                detail="recent strong Human Sovereign re-authentication required",
            )

    payload = await _request_payload(request)
    _validate_json_body_against_route(request, payload)
    path_params = dict(getattr(request, "path_params", {}) or {})
    resource = _resource_for(path, path_params, payload)
    envelope_principal = EnvelopePrincipal(
        session_id=principal.session_id if principal else None,
        actor_source=authority.actor_source,
        client_ip=(
            principal.client_address
            if principal
            else (request.client.host if request.client else "")
        ),
    )
    mission_id = (
        path_params.get("mission_id")
        or payload.get("mission_id")
        or payload.get("missionId")
    )
    contract_digest = payload.get("contract_digest") or payload.get("contractDigest")
    # Council mission identifiers and contract digests are authority metadata,
    # not user-controlled action content. Keep them in the immutable
    # envelope/capability binding while excluding them from the secret-scanned
    # action payload (the scanner intentionally treats high-entropy identifiers
    # as credential-like).
    if path in {"/api/v1/council/approve", "/api/v1/council/reject"}:
        payload = {
            key: value
            for key, value in payload.items()
            if str(key).lower()
            not in {
                "contract_digest",
                "contractdigest",
                "mission_id",
                "missionid",
            }
        }
    envelope = ActionEnvelope(
        route=path,
        action_type=authority.action_type,
        http_method=request.method,
        payload=payload,
        principal=envelope_principal,
        request_id=request.headers.get("x-request-id"),
        operator_id=principal.principal_id if principal else None,
        device_id=principal.device_id if principal else None,
        authentication_event_id=principal.authentication_event_id
        if principal
        else None,
        mission_id=str(mission_id) if mission_id is not None else None,
        contract_digest=str(contract_digest) if contract_digest is not None else None,
        resource=resource,
        policy_version=authority.policy_version,
        data_classification="PROJECT_INTERNAL",
        requested_capability=f"route.{authority.action_type.value}",
        correlation_id=(
            request.headers.get("x-correlation-id")
            or request.headers.get("x-request-id")
            or str(uuid.uuid4())
        ),
    )

    binding = _binding_for(envelope, principal) if principal else None
    token = request.headers.get(CAPABILITY_HEADER)
    if (
        path == _EMERGENCY_CLEAR_ROUTE
        and authority.action_type is ActionType.EMERGENCY_STOP_CLEAR
    ):
        if principal is None or binding is None:
            raise HTTPException(
                status_code=401, detail="authenticated operator session required"
            )
        stop = get_emergency_stop()
        if token is None:
            try:
                token = stop.issue_clear_capability(
                    operator_id=principal.principal_id,
                    authentication_event_id=principal.authentication_event_id,
                    session_id=principal.session_id,
                )
            except Exception as exc:  # noqa: BLE001 - governance refuses closed
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            raise HTTPException(
                status_code=428,
                detail={
                    "error": "exact_emergency_clear_capability_required",
                    "route": path,
                    "approvalToken": token,
                    "reason": "new privileged authentication event required",
                },
            )
        request.state.action_guard = ActionGuardResult(
            envelope=envelope,
            decision=None,
            capability_digest=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        )
        return request.state.action_guard
    try:
        decision = broker.submit(
            envelope,
            capability_token=token,
            capability_binding=binding,
            issue_capability=authority.authority_class == "YELLOW",
        )
    except (EmergencyStopError, PolicyBrokerError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if decision.blocked:
        status_code = 429 if decision.audit_event == "rate_limit" else 403
        raise HTTPException(status_code=status_code, detail=decision.reason)
    if decision.requires_approval:
        raise HTTPException(
            status_code=428,
            detail={
                "error": "exact_capability_required",
                "route": path,
                "approvalToken": decision.approval_token,
                "reason": decision.reason,
            },
        )
    if not decision.allowed:
        raise HTTPException(status_code=403, detail="action was not authorised")

    result = ActionGuardResult(
        envelope=envelope,
        decision=decision,
        capability_digest=(
            hashlib.sha256(token.encode("utf-8")).hexdigest() if token else None
        ),
    )
    request.state.action_guard = result
    if getattr(decision, "consumed_capability_proof", None) is not None:
        request.state.consumed_capability_proof = decision.consumed_capability_proof
    return result


__all__ = ["ActionGuardResult", "CAPABILITY_HEADER", "enforce_action_boundary"]
