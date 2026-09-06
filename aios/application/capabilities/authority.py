"""Server-issued exact capability authority."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from aios.domain.capabilities.contracts import (
    Capability,
    CapabilityBinding,
    ConsumedCapabilityProof,
)
from aios.domain.capabilities.digest import payload_digest
from aios.infrastructure.capabilities.sqlite_store import CapabilityStore
from aios.security.secret_scanner import scan_and_redact


# Resource/authority metadata is already bound into the capability digest and
# resource digest.  Its opaque path/session/mission identifiers can contain
# runner-generated entropy (notably pytest's POSIX temp paths), which must not
# be mistaken for credential material.  Named secret patterns are still
# scanned for these fields; only the generic entropy pass is ignored.
_RESOURCE_METADATA_KEYS = frozenset(
    {
        "path",
        "filepath",
        "filePath",
        "root",
        "workspaceRoot",
        "workspace_root",
        "sourceId",
        "source_id",
        "missionId",
        "mission_id",
        "proposalId",
        "proposal_id",
        "snapshotId",
        "snapshot_id",
        "workerId",
        "worker_id",
        "sessionId",
        "session_id",
        "contractDigest",
        "contract_digest",
    }
)

#: A git object id: exactly 40 lowercase hex characters.
_GIT_OBJECT_ID = re.compile(r"[0-9a-f]{40}")

#: Findings tolerated on bound resource metadata whose value is a git object
#: id -- in addition to HIGH_ENTROPY, which is tolerated on all such metadata.
#:
#: WHY: `snapshot_id` on the Council rollback path is a git commit sha. The
#: scanner's AWS_SECRET_KEY rule is a deliberately broad catch-all --
#: `\b[A-Za-z0-9/+=]{40}\b` -- gated on an AWS keyword appearing within 100
#: characters. A lone 40-char sha IS that whole window, and exactly one of the
#: gate's keywords is spellable in hex: "ec2" (e, c, 2). So a sha that happens
#: to contain "ec2" opens the gate and then matches the catch-all, and the
#: rollback is refused with a credential warning about a plain commit id.
#:
#: Measured, not estimated: 1925 of 200000 random 40-hex shas contain "ec2"
#: (0.96%, ~1 run in 104). That is the intermittent failure previously
#: recorded as an "order-dependent flake" -- it is neither order- nor
#: platform-dependent, just a ~1% dice roll on the sha.
#:
#: Why this is narrow rather than a weakened guard: it applies only to keys
#: already in `_RESOURCE_METADATA_KEYS` (bound into the capability and
#: resource digests), only to the exact 40-lowercase-hex shape, and only to
#: the unlabelled catch-all -- never to a specific provider pattern. Those
#: fields already tolerate HIGH_ENTROPY by design, so opaque high-entropy ids
#: were always permitted here; a real AWS secret access key uses the full
#: mixed-case base64 alphabet and is not all-lowercase-hex.
#:
#: The scanner itself is untouched: aios/security/secret_scanner.py is FROZEN
#: CORE (AGENTS.md SXI), and its behaviour is correct for its own contract --
#: the false positive belongs to this call site, which knows the value is a
#: commit id and the scanner does not.
_GIT_ID_TOLERATED_FINDINGS = frozenset({"AWS_SECRET_KEY"})


def _action_payload_secret_findings(payload: dict[str, Any]) -> tuple[str, ...]:
    """Findings that make this payload look credential-bearing, or ``()``.

    Returns WHY rather than just whether. The refusal this feeds says only
    "contains credential-like data", naming neither the detector that fired
    nor the field it fired on. That leaves an operator holding a refused
    action and no way to tell a real leak from a false positive without
    re-deriving the scan by hand.

    Only finding NAMES and field KEYS are returned -- never the offending
    value, which is the thing suspected of being a secret.

    This is a diagnosability change, not a bug fix: no known failure is
    attributed to this scan. It is a guard whose output was unreadable.
    """

    findings: list[str] = []

    def mask_resource_metadata(value: Any, *, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {
                name: mask_resource_metadata(child, key=str(name))
                for name, child in value.items()
            }
        if isinstance(value, list):
            return [mask_resource_metadata(child, key=key) for child in value]
        if key in _RESOURCE_METADATA_KEYS and isinstance(value, str):
            metadata_scan = scan_and_redact(value)
            # HIGH_ENTROPY is tolerated on bound resource metadata: ids, paths
            # and digests are legitimately high-entropy. A NAMED credential
            # pattern is not tolerated even here -- except the unlabelled
            # AWS_SECRET_KEY catch-all on a value that is exactly a git object
            # id, which is a commit sha and not a credential. See
            # _GIT_ID_TOLERATED_FINDINGS for why that is narrow.
            tolerated = {"HIGH_ENTROPY"}
            if _GIT_OBJECT_ID.fullmatch(value):
                tolerated |= _GIT_ID_TOLERATED_FINDINGS
            findings.extend(
                f"{key}:{finding}"
                for finding in metadata_scan.findings
                if finding not in tolerated
            )
            return "<bound-resource-metadata>"
        return value

    masked = mask_resource_metadata(payload)
    content_scan = scan_and_redact(
        json.dumps(masked, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )
    if content_scan.detected:
        findings.extend(f"payload:{finding}" for finding in content_scan.findings)
    return tuple(dict.fromkeys(findings))


def _action_payload_contains_secret(payload: dict[str, Any]) -> bool:
    """Whether this payload looks credential-bearing.

    Kept as the boolean predicate other call sites already use;
    :func:`_action_payload_secret_findings` is the same check with the reason
    attached.
    """
    return bool(_action_payload_secret_findings(payload))


class CapabilityError(RuntimeError):
    """Raised when a capability is missing, altered, expired, or revoked."""


class EmergencyStopHardWiringAuthority:
    """Own the fail-closed policy for every injected emergency-stop boundary.

    The durable latch remains :class:`EmergencyStopController`'s mechanism. This
    owner makes the application boundary explicit: an optional stop is allowed
    only for deliberately isolated fixtures, while a supplied dependency must
    expose the real ``assert_operational`` method before any side effect.
    """

    #: Explicit opt-out for deliberately ungoverned fixtures.
    #:
    #: `None` and "this fixture does not need a latch" used to be the same
    #: value, so a production path that simply FORGOT the stop was
    #: indistinguishable from one that had opted out on purpose. That is how
    #: `get_self_apply_engine` shipped a verify executor with no latch: nothing
    #: could tell the omission from a choice. Naming the choice makes the
    #: omission visible.
    UNGOVERNED_FIXTURE = "ungoverned-fixture"

    @staticmethod
    def assert_operational(emergency_stop: Any | None, *, boundary: str) -> None:
        """Check a latch that MAY legitimately be absent (unchanged behaviour).

        Kept lenient on `None` because hundreds of unit fixtures construct
        governed objects without a latch and are not production. Use
        :meth:`require_wired` at the wiring boundary, where absence is always a
        bug rather than a choice.
        """
        if emergency_stop is None:
            return
        checker = getattr(emergency_stop, "assert_operational", None)
        if not callable(checker):
            raise TypeError(
                f"{boundary} emergency-stop dependency is not operationally checkable"
            )
        checker()

    @classmethod
    def require_wired(cls, emergency_stop: Any | None, *, boundary: str) -> Any:
        """Fail at WIRING TIME when a governed production object has no latch.

        `aios/core/executor.py` guards with `if self.emergency_stop is not
        None:` -- so an absent latch is not a wrong answer, it is *no question
        asked*, and the executor dispatches. Measured 2026-09-06: the
        self-apply verify executor was built without one, meaning engaging the
        emergency stop did not halt self-apply verification at all.

        That file is FOUNDATION_LOCK'd and its guard is correct for the objects
        that may legitimately lack a latch. The place to make omission
        impossible is where PRODUCTION objects are built -- `aios/api/deps.py`
        -- because a production path has no honest reason to be ungoverned.

        Returns the latch so it can be used inline at a construction site.
        """
        if emergency_stop is cls.UNGOVERNED_FIXTURE:
            return None
        if emergency_stop is None:
            raise RuntimeError(
                f"{boundary} was constructed without an emergency stop. A "
                "governed production object must be able to be halted; pass "
                "get_emergency_stop(), or "
                "EmergencyStopHardWiringAuthority.UNGOVERNED_FIXTURE to state "
                "that ungoverned is deliberate."
            )
        cls.assert_operational(emergency_stop, boundary=boundary)
        return emergency_stop


class CapabilityAuthority:
    """Issue and atomically consume opaque capabilities bound to one action."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        ttl_seconds: float = 120.0,
        clock: Callable[[], float] = time.time,
        emergency_stop: Any | None = None,
        constitution_authority: Any | None = None,
        authentication_event_lookup: Callable[[str], Any] | None = None,
    ) -> None:
        self.store = CapabilityStore(db_path)
        self.ttl_seconds = max(float(ttl_seconds), 0.001)
        self.clock = clock
        self.emergency_stop = emergency_stop
        #: Organ 25. Late-bindable, matching `emergency_stop`'s existing
        #: convention -- `aios/api/deps.py` sets it on the singleton.
        self.constitution_authority = constitution_authority
        #: INVARIANT III. Resolves an authentication_event_id to its stored
        #: record so `consume` can ask whether the human authenticated AFTER
        #: the action was requested. Late-bound the same way, because the
        #: identity store lives a layer above this one.
        self.authentication_event_lookup = authentication_event_lookup

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def issue(
        self,
        binding: CapabilityBinding,
        *,
        action_payload: dict[str, Any] | None = None,
    ) -> str:
        EmergencyStopHardWiringAuthority.assert_operational(
            self.emergency_stop, boundary="capability-authority"
        )
        if "*" in binding.scope:
            raise CapabilityError("wildcard capability scope is forbidden")
        if action_payload is not None:
            if payload_digest(action_payload) != binding.payload_digest:
                raise CapabilityError(
                    "capability action payload does not match its digest"
                )
            secret_findings = _action_payload_secret_findings(action_payload)
            if secret_findings:
                raise CapabilityError(
                    "capability action payload contains credential-like data "
                    f"({', '.join(secret_findings)})"
                )
        now = self.clock()
        token = secrets.token_urlsafe(32)
        capability = Capability(
            capability_id=f"capability:{uuid.uuid4().hex}",
            binding=binding,
            issued_at=now,
            expires_at=now + self.ttl_seconds,
            nonce=secrets.token_urlsafe(16),
            action_payload=dict(action_payload) if action_payload is not None else None,
        )
        try:
            self.store.insert(capability, self._token_digest(token))
        except Exception as exc:  # noqa: BLE001 - authority fails closed
            raise CapabilityError("capability issuance failed") from exc
        return token

    def inspect(self, token: str) -> Capability:
        capability = self.store.by_token_digest(self._token_digest(token))
        if capability is None:
            raise CapabilityError("capability is unknown")
        return capability

    def _requires_fresh_authentication(self, capability: Capability) -> bool:
        """True when approving this action must follow a NEW human authentication.

        Scoped to actions that FETCH AND EXECUTE REMOTE CODE (`pip install`,
        `npm install`, `git clone` ...), by operator decision on 2026-09-06.
        Ordinary YELLOW work -- `mkdir`, `touch`, `pytest` -- stays one click,
        because requiring a re-authentication per `mkdir` would be unusable and
        an unusable control gets switched off.

        The other half of the high-risk class needs nothing here: writes outside
        the sandbox are already RED, and RED is refused even under approval
        (measured -- `touch ../../outside.txt` returns control=execute_approved).
        So the class reduces to network fetches.

        This deliberately reads the ACTION, not the zone. Zone answers "how
        destructive locally"; this asks "does approving it also approve running
        someone else's code", which is a different question.
        """
        payload = capability.action_payload or {}
        command = payload.get("command")
        if not isinstance(command, str) or not command.strip():
            return False
        # Imported lazily: the policy kernel sits above this layer, and a
        # module-level import would couple the capability authority to it.
        from aios.policy.kernel import requires_network_capability

        return requires_network_capability(command)

    def _assert_authentication_is_newer(
        self, issued: CapabilityBinding, presented: CapabilityBinding
    ) -> None:
        """The approving human must have authenticated AFTER the request.

        An agent replaying the token it was just handed still holds the auth
        event that made the request, so it cannot satisfy this. A human who
        re-authenticates creates a newer one and proceeds. That is the whole
        difference between consent and replay.

        "Newer", not merely "different": without the timestamp check, an
        attacker holding any OTHER event -- an older one, or one from an
        unrelated session -- would satisfy a difference test.
        """
        if issued.authentication_event_id == presented.authentication_event_id:
            raise CapabilityError(
                "this action fetches and executes remote code, so approving it "
                "requires a NEW privileged authentication event: the principal "
                "that requested it cannot also authorise it"
            )
        lookup = self.authentication_event_lookup
        if lookup is None:
            # FAIL CLOSED. Unable to compare is not permission to proceed --
            # and this path is exactly where a mis-wired singleton would
            # otherwise silently restore the behaviour being fixed.
            raise CapabilityError(
                "authentication-event freshness cannot be verified; refusing a "
                "high-risk capability rather than assuming consent"
            )
        try:
            issued_event = lookup(issued.authentication_event_id)
            presented_event = lookup(presented.authentication_event_id)
        except Exception as exc:  # noqa: BLE001 - a degraded store is not consent
            raise CapabilityError(
                "authentication-event lookup is degraded; refusing a high-risk "
                "capability"
            ) from exc
        if not issued_event or not presented_event:
            raise CapabilityError(
                "authentication events for this capability are unknown; "
                "refusing a high-risk capability"
            )
        issued_at = float(issued_event.get("created_at") or 0.0)
        presented_at = float(presented_event.get("created_at") or 0.0)
        if presented_at <= issued_at:
            raise CapabilityError(
                "the authentication presented is not newer than the one that "
                "requested this action; re-authenticate to approve it"
            )

    def consume(
        self, token: str, binding: CapabilityBinding
    ) -> ConsumedCapabilityProof:
        EmergencyStopHardWiringAuthority.assert_operational(
            self.emergency_stop, boundary="capability-authority"
        )
        capability = self.inspect(token)
        now = self.clock()
        # INVARIANT III: the principal that REQUESTS an action must not be able
        # to authorise it. `action_guard` hands the approval token back to the
        # caller that just asked, so for high-risk actions one principal could
        # request and approve with no human anywhere -- and the resulting audit
        # row was indistinguishable from genuine operator consent. Both wrote
        # "approved". A record that cannot tell those apart is not consent.
        fresh_required = self._requires_fresh_authentication(capability)
        # constitution_digest reflects "what was live when this side was
        # built" for both the stored binding (issue time) and the caller's
        # freshly-reconstructed one (this consume request, from a live
        # Principal) -- it is not part of "is this literally the same
        # requested action" and is checked for staleness separately below,
        # so a real callable amendment during the TTL window surfaces as
        # the specific stale-constitution error rather than a generic
        # binding mismatch.
        #
        # authentication_event_id is excluded for high-risk actions, and that
        # exclusion is the WHOLE fix rather than a loosening. The binding
        # normally pins the exact auth event, so a human who re-authenticated
        # would find their approval REJECTED as a mismatch -- meaning the only
        # way to approve was to still hold the event that made the request.
        # The rule that looked like strictness was what forced self-approval.
        # Here it is inverted: the event must differ, and differ by being NEWER
        # (asserted immediately below, so "differ" cannot be met by an older
        # or unrelated event).
        _ignored: dict[str, Any] = {"constitution_digest": None}
        if fresh_required:
            _ignored["authentication_event_id"] = "*"
        if replace(capability.binding, **_ignored) != replace(binding, **_ignored):
            raise CapabilityError("capability binding mismatch")
        if fresh_required:
            self._assert_authentication_is_newer(capability.binding, binding)
        if capability.binding.constitution_digest is not None:
            # Organ 24/25: reject outright rather than downgrade -- a
            # capability issued under a constitution that has since been
            # amended must never be honored, even if it hasn't expired.
            #
            # This used to rebuild the "current" digest from live config. The
            # binding's own digest was produced the same way, so both sides
            # always matched and this rejection could never fire for a real
            # amendment. It now reads the durable chain, which actually moves
            # when an amendment activates.
            if self.constitution_authority is None:
                raise CapabilityError(
                    "no constitution authority is wired; refusing to consume a "
                    "constitution-bound capability without verifying it"
                )
            current_digest = self.constitution_authority.get_active_snapshot(
                capability.binding.operator_id
            ).snapshot_digest
            if current_digest != capability.binding.constitution_digest:
                raise CapabilityError(
                    "capability was issued under a stale constitution; "
                    "re-authenticate and retry"
                )
        if capability.revoked_at is not None:
            raise CapabilityError("capability revoked")
        if capability.consumed_at is not None:
            raise CapabilityError("capability already consumed")
        if capability.expires_at <= now:
            raise CapabilityError("capability expired")
        if not self.store.consume_if_available(capability.capability_id, now):
            raise CapabilityError("capability already consumed, revoked, or expired")
        token_dig = self._token_digest(token)
        return ConsumedCapabilityProof(
            capability_id=capability.capability_id,
            token_digest=token_dig,
            operator_id=capability.binding.operator_id,
            device_id=capability.binding.device_id,
            authentication_event_id=capability.binding.authentication_event_id,
            session_id=capability.binding.session_id,
            action_type=capability.binding.action_type,
            route=capability.binding.route,
            http_method=capability.binding.http_method,
            payload_digest=capability.binding.payload_digest,
            resource_digest=capability.binding.resource_digest,
            mission_id=capability.binding.mission_id,
            contract_digest=capability.binding.contract_digest,
            policy_version=capability.binding.policy_version,
            scope=capability.binding.scope,
            verification_requirement=capability.binding.verification_requirement,
            consumed_at=now,
            expires_at=capability.expires_at,
            revoked_at=capability.revoked_at,
            constitution_digest=capability.binding.constitution_digest,
        )

    def revoke(self, capability_id: str) -> None:
        if not self.store.revoke(capability_id, self.clock()):
            raise CapabilityError("capability is unavailable for revocation")

    def clear_grants(self, session_id: str, *, route: str) -> None:
        """Start a fresh replay chain without deleting the audit records."""
        if not session_id or not route:
            raise CapabilityError("grant cursor requires a session and route")
        self.store.clear_grants(session_id, route, self.clock())

    def grants(self, session_id: str, *, route: str) -> list[Capability]:
        """Return still-live consumed capabilities in the current replay chain."""
        if not session_id or not route:
            raise CapabilityError("grant lookup requires a session and route")
        return self.store.consumed_for_session(session_id, route, self.clock())

    def has_any_grant(self) -> bool:
        """Return whether the operator has ever consumed an exact capability."""
        return self.store.has_consumed()

    def consumed_count(self) -> int:
        """Return the durable number of consumed exact capabilities."""
        return self.store.consumed_count()

    def list_pending(self) -> list[Capability]:
        """Return every capability currently awaiting consumption -- the
        real production approval-decision surface (organ 47/49). Never
        exposes a usable bearer token; a read-only awareness enumeration."""
        return self.store.pending(self.clock())

    def revoke_all_active(self) -> int:
        """Revoke every still-live unconsumed capability."""
        return self.store.revoke_all_active(self.clock())
