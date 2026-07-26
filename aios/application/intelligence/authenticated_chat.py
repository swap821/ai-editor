"""Authenticated conversational representation for PR2.

This application service is deliberately the only authenticated-chat adapter
that may assemble human-representation sources and enter the streaming
intelligence gateway.  It never reads legacy raw fact/recall prompt blocks;
those remain available only to the compatibility path for anonymous chat.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from aios.application.intelligence.gateway import (
    IntelligenceGatewayError,
    StreamingIntelligenceGatewayResult,
    stream_intelligence_request,
)
from aios.application.governance.organ_ledger import current_commit_sha
from aios.application.memory.human_representation import (
    is_operator_preference_expired,
    is_project_passport_stale,
)
from aios.application.turns.turn_context import TurnContext
from aios.core.failover import FailoverChatClient
from aios.domain.identity.models import Principal, PrincipalType
from aios.domain.intelligence.representative_context import (
    ContextExclusionV1,
    RepresentativeContextReceiptV1,
)
from aios.domain.memory.human_representation import (
    HumanStateHypothesis,
    OperatorPreferenceV1,
    ProjectPassportV1,
)
from aios.application.intelligence.transport_target import (
    classify_transport,
    is_loopback_http_url,
)
from aios.infrastructure.identity.sqlite_store import credential_digest

_HUMAN_STATE_MIN_CONFIDENCE = 0.60
_RECEIPT_TTL = timedelta(minutes=5)


class AuthenticatedChatRepresentationError(IntelligenceGatewayError):
    """Fail-closed refusal while resolving authenticated chat sources."""


@dataclass(slots=True)
class AuthenticatedChatRepresentation:
    """Resolve authenticated sources, persist a receipt, and stream via Organ 32."""

    principal: Principal
    constitution_authority: Any
    preference_store: Any
    project_passport_store: Any
    correction_store: Any
    conversation_state: Any
    representative_context_store: Any
    emergency_stop: Any
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    current_commit_lookup: Callable[[str], str | None] = current_commit_sha

    def stream(
        self,
        *,
        context: TurnContext,
        user_text: str,
        task: str,
        provider: str,
        chat_client: Any,
        model: str,
        human_state: HumanStateHypothesis,
        human_state_hypothesis_id: int | None,
        stream_chat_chunks: Callable[..., Iterator[str]],
        chat_system_prompt: str,
    ) -> StreamingIntelligenceGatewayResult:
        """Compile and persist before exposing any provider-produced chunk."""
        try:
            target = self._resolve_target(provider=provider, chat_client=chat_client)
            constitution_digest = self._validated_constitution_digest()
            (
                preferences,
                preference_ids,
                passport,
                passport_revision,
                correction_ids,
                current_decisions,
                exclusions,
            ) = self._resolve_sources(
                context=context,
                human_state=human_state,
                human_state_hypothesis_id=human_state_hypothesis_id,
            )
            identity_digest = credential_digest(self.principal.principal_id)
            now = self._utc_now()
            expires_at = now + _RECEIPT_TTL
            consent_scope = ["authenticated-chat", f"target:{target}"]
            if passport is not None:
                consent_scope.append(f"project:{passport.project_id}")

            def _receipt_for(compiled_context):
                return RepresentativeContextReceiptV1.create(
                    request_id=compiled_context.request_id,
                    context_digest=compiled_context.context_digest,
                    operator_identity_digest=identity_digest,
                    constitution_digest=constitution_digest,
                    target=target,
                    active_project_revision=passport_revision,
                    included_preference_ids=preference_ids,
                    included_correction_ids=correction_ids,
                    human_state_hypothesis_id=human_state_hypothesis_id,
                    human_state_disposition=(
                        "included"
                        if self._should_include_human_state(
                            human_state, human_state_hypothesis_id
                        )
                        else "abstained"
                    ),
                    exclusions=tuple(exclusions),
                    # Truthful per turn: a loopback turn needs no consent, a
                    # cloud turn is permitted by the operator's own standing
                    # egress policy (AIOS_ROUTER_CLOUD_TASKS), which is what
                    # let the router choose a cloud provider in the first place.
                    consent_status=(
                        "not_required_local"
                        if target == "local"
                        else "policy_permitted_cloud"
                    ),
                    consent_scope=tuple(consent_scope),
                    created_at=now.isoformat(),
                    expires_at=expires_at.isoformat(),
                )

            def _model_call(compiled_context):
                rendered_context = json.dumps(
                    compiled_context.as_dict(), sort_keys=True, ensure_ascii=True
                )
                messages = [
                    {
                        "role": "system",
                        "content": (
                            f"{chat_system_prompt}\n\n"
                            "Authenticated representative context (the only "
                            f"personalization source for this reply):\n{rendered_context}"
                        ),
                    },
                    {"role": "user", "content": compiled_context.goal},
                ]
                return stream_chat_chunks(chat_client, messages, model=model)

            return stream_intelligence_request(
                request_id=context.turn_id,
                operator_identity_digest=identity_digest,
                constitution_digest=constitution_digest,
                goal=user_text,
                desired_outcome="Provide a safe, conversational response to the authenticated operator.",
                target=target,
                delegated_authority_summary=(
                    "Authenticated conversation reply only; no tool, file, or execution authority."
                ),
                model_call=_model_call,
                explicit_constraints=(
                    "Conversation only; do not claim tool or execution authority.",
                ),
                current_decisions=tuple(current_decisions),
                active_preferences=preferences,
                project_passport=passport,
                project_passport_stale=False,
                communication_mode="direct",
                emergency_stop=self.emergency_stop,
                context_store=self.representative_context_store,
                receipt_factory=_receipt_for,
                require_context_receipt=True,
            )
        except IntelligenceGatewayError:
            raise
        except Exception as exc:  # noqa: BLE001 - authenticated source failure is fatal
            raise AuthenticatedChatRepresentationError(
                "authenticated representative context could not be resolved"
            ) from exc

    def _resolve_target(self, *, provider: str, chat_client: Any) -> str:
        """Classify this turn's transport as ``"local"`` or ``"cloud"``.

        This used to REFUSE anything that was not loopback Ollama, and the
        pipeline treats that refusal as fatal -- so an authenticated operator
        asking a coding or reasoning question (both of which
        ``AIOS_ROUTER_CLOUD_TASKS`` permits to route to a cloud provider by
        default) got an error instead of a reply, and the multi-provider router
        was unusable while signed in.

        The decision itself now lives in ``transport_target.classify_transport``
        so this adapter and Council's cannot drift apart on it.
        """
        if isinstance(chat_client, FailoverChatClient):
            candidates = chat_client.candidates
            if not candidates:
                raise AuthenticatedChatRepresentationError(
                    "authenticated representative chat cannot resolve an empty "
                    "failover candidate list"
                )
            clients: list[Any] = []
            for candidate in candidates:
                if (
                    not isinstance(candidate, tuple)
                    or len(candidate) != 3
                    or str(candidate[2]).strip().lower() != "ollama"
                ):
                    # Any non-ollama fallback in the chain can serve this turn,
                    # so the whole turn is classified by its weakest link.
                    return "cloud"
                clients.append(candidate[0])
        else:
            clients = [chat_client]
        return classify_transport(provider=provider, clients=clients)

    @staticmethod
    def _is_loopback_ollama_host(raw_host: object) -> bool:
        """Delegates to the shared classifier so this adapter and Council's
        cannot drift apart on what counts as local."""
        return is_loopback_http_url(raw_host)

    def _validated_constitution_digest(self) -> str:
        if self.principal.principal_type is not PrincipalType.OPERATOR:
            raise AuthenticatedChatRepresentationError(
                "authenticated representative chat requires an operator principal"
            )
        if not self.principal.session_id or not self.principal.constitution_digest:
            raise AuthenticatedChatRepresentationError(
                "authenticated session lacks constitution binding"
            )
        snapshot = self.constitution_authority.get_active_snapshot(
            self.principal.principal_id
        )
        if (
            snapshot.ratified_by_operator_id != self.principal.principal_id
            or snapshot.snapshot_digest != self.principal.constitution_digest
        ):
            raise AuthenticatedChatRepresentationError(
                "authenticated session constitution binding is stale"
            )
        return str(snapshot.snapshot_digest)

    def _resolve_sources(
        self,
        *,
        context: TurnContext,
        human_state: HumanStateHypothesis,
        human_state_hypothesis_id: int | None,
    ) -> tuple[
        tuple[OperatorPreferenceV1, ...],
        tuple[str, ...],
        ProjectPassportV1 | None,
        int | None,
        tuple[str, ...],
        list[str],
        list[ContextExclusionV1],
    ]:
        owner_digest = credential_digest(self.principal.principal_id)
        exclusions: list[ContextExclusionV1] = []
        current_decisions: list[str] = []

        active_project = self.project_passport_store.get_active_for_operator(
            owner_digest
        )
        passport: ProjectPassportV1 | None = None
        passport_revision: int | None = None
        project_scope: str | None = None
        if active_project is None:
            exclusions.append(
                ContextExclusionV1(
                    source="project_passport",
                    field="active_project",
                    reason="unavailable",
                )
            )
        else:
            project_id, summary = active_project
            current_passport = self.project_passport_store.get_current_with_revision(
                project_id
            )
            if current_passport is None:
                exclusions.append(
                    ContextExclusionV1(
                        source="project_passport",
                        field="active_project",
                        source_id=project_id,
                        reason="unavailable",
                    )
                )
            else:
                candidate_revision, candidate_passport = current_passport
                root = summary.get("root")
                current_commit: str | None = None
                if isinstance(root, str) and root:
                    try:
                        current_commit = self.current_commit_lookup(root)
                    except Exception:  # noqa: BLE001 - missing proof is stale
                        current_commit = None
                if is_project_passport_stale(
                    candidate_passport, current_commit_sha=current_commit
                ):
                    raise AuthenticatedChatRepresentationError(
                        "authenticated project passport is stale or unverified"
                    )
                passport_revision, passport = candidate_revision, candidate_passport
                project_scope = f"project:{project_id}"
                current_decisions.append(
                    self._passport_decision(passport, passport_revision)
                )
        preferences, preference_ids, preference_exclusions = self._select_preferences(
            owner_digest=owner_digest,
            project_scope=project_scope,
        )
        exclusions.extend(preference_exclusions)

        active_revision = self.conversation_state.active_correction_revision(
            self.principal.session_id
        )
        correction = self.correction_store.verified_active_projection(
            session_id=self.principal.session_id,
            operator_id=self.principal.principal_id,
            operator_identity_digest=owner_digest,
            authentication_event_id=self.principal.authentication_event_id,
            active_revision=active_revision,
        )
        correction_ids: tuple[str, ...] = ()
        if correction is None:
            exclusions.append(
                ContextExclusionV1(
                    source="correction_lineage",
                    field="active_correction",
                    reason="unavailable",
                )
            )
        else:
            event, corrected_values = correction
            correction_ids = (str(event.event_id),)
            for field, value in sorted(corrected_values.items()):
                current_decisions.append(f"Authenticated correction ({field}): {value}")

        if self._should_include_human_state(human_state, human_state_hypothesis_id):
            current_decisions.append(
                "Advisory human state: "
                f"{human_state.state} (confidence={human_state.confidence:.2f}); "
                f"reason={human_state.visible_reason}"
            )
        else:
            exclusions.append(
                ContextExclusionV1(
                    source="human_state",
                    field="current_turn",
                    source_id=(
                        str(human_state_hypothesis_id)
                        if human_state_hypothesis_id is not None
                        else None
                    ),
                    reason=(
                        "below_confidence_threshold"
                        if human_state_hypothesis_id is not None
                        else "unavailable"
                    ),
                )
            )

        return (
            preferences,
            preference_ids,
            passport,
            passport_revision,
            correction_ids,
            current_decisions,
            exclusions,
        )

    def _select_preferences(
        self, *, owner_digest: str, project_scope: str | None
    ) -> tuple[
        tuple[OperatorPreferenceV1, ...],
        tuple[str, ...],
        list[ContextExclusionV1],
    ]:
        exclusions: list[ContextExclusionV1] = []
        selected: dict[tuple[str, str], OperatorPreferenceV1] = {}
        scopes = ["global"]
        if project_scope is not None:
            scopes.append(project_scope)
        for scope in scopes:
            for pref in self.preference_store.list_for_operator_scope(
                owner_digest, scope
            ):
                reason = self._excluded_preference_reason(pref)
                if reason is not None:
                    exclusions.append(
                        ContextExclusionV1(
                            source="operator_preference",
                            field=f"{pref.domain}.{pref.key}",
                            source_id=pref.preference_id,
                            reason=reason,
                        )
                    )
                    continue
                preference_key = (pref.domain, pref.key)
                previous = selected.get(preference_key)
                if previous is not None:
                    exclusions.append(
                        ContextExclusionV1(
                            source="operator_preference",
                            field=f"{previous.domain}.{previous.key}",
                            source_id=previous.preference_id,
                            reason="superseded",
                        )
                    )
                selected[preference_key] = pref
        values = tuple(selected.values())
        return values, tuple(pref.preference_id for pref in values), exclusions

    @staticmethod
    def _excluded_preference_reason(pref: OperatorPreferenceV1) -> str | None:
        if pref.status == "withdrawn":
            return "withdrawn"
        if pref.status in {"superseded", "rejected"}:
            return "superseded"
        if pref.status != "active":
            return "unavailable"
        if is_operator_preference_expired(pref):
            return "expired"
        return None

    @staticmethod
    def _should_include_human_state(
        hypothesis: HumanStateHypothesis, hypothesis_id: int | None
    ) -> bool:
        return (
            hypothesis_id is not None
            and hypothesis.confidence >= _HUMAN_STATE_MIN_CONFIDENCE
        )

    @staticmethod
    def _passport_decision(passport: ProjectPassportV1, revision: int) -> str:
        def compact(value: str, limit: int = 400) -> str:
            return " ".join(value.split())[:limit]

        pieces = [
            f"Active project passport revision {revision}",
            f"goal={compact(passport.goal)}",
            f"architecture={compact(passport.architecture_summary)}",
        ]
        if passport.current_phase:
            pieces.append(f"phase={compact(passport.current_phase, 160)}")
        if passport.invariants:
            pieces.append(
                "invariants="
                + "; ".join(compact(item, 120) for item in passport.invariants[:4])
            )
        return "; ".join(pieces)

    def _utc_now(self) -> datetime:
        value = self.now()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


__all__ = ["AuthenticatedChatRepresentation", "AuthenticatedChatRepresentationError"]
