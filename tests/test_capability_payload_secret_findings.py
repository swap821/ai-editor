"""The capability payload refusal must say WHY.

`CapabilityAuthority.issue()` refuses a payload that looks credential-bearing.
That refusal used to read only "capability action payload contains
credential-like data" -- naming neither the detector that fired nor the field
it fired on -- so an operator holding a refused action could not tell a real
leak from a false positive without re-deriving the scan by hand.

No known failure is attributed to this scan; it is a guard whose output was
unreadable, not a broken one. These tests pin what it actually does, so a
future refusal can be read rather than guessed at.

The tolerance rule they cover is subtle and was previously untested:
HIGH_ENTROPY is tolerated on bound resource metadata (ids, paths and digests
are legitimately high-entropy) but a NAMED credential pattern is refused even
there.
"""

from __future__ import annotations

import pytest

from aios.application.capabilities.authority import (
    _action_payload_contains_secret,
    _action_payload_secret_findings,
)

#: A macOS pytest temp path. Constructed literally rather than taken from the
#: runner's tmp dir, so this exercises the macOS shape on every platform --
#: otherwise the case only ever runs on macOS, which is where it was missed.
_MACOS_TMP = (
    "/var/folders/k1/8mz_9qxn5t34b7_qx1z0000gn/T/pytest-of-runner/pytest-0/test_x0/repo"
)
_LINUX_TMP = "/tmp/pytest-of-runner/pytest-0/test_x0/repo"
_GIT_SHA = "e15442c48d1f7000af3761c79d86052db5689d9d"


# --------------------------------------------------------------------------- #
# Legitimate payloads are accepted
# --------------------------------------------------------------------------- #


def test_a_council_rollback_payload_is_accepted() -> None:
    """The exact payload shape /council/missions/{id}/rollback issues."""
    assert (
        _action_payload_secret_findings(
            {"mission_id": "mission-abc", "snapshot_id": _GIT_SHA}
        )
        == ()
    )


@pytest.mark.parametrize("tmp_path_value", [_MACOS_TMP, _LINUX_TMP])
def test_a_temp_path_in_bound_metadata_is_tolerated(tmp_path_value: str) -> None:
    """A macOS `/var/folders/<id>/T/...` path carries enough entropy to trip
    the HIGH_ENTROPY detector on its own, while a Linux `/tmp/...` path does
    not. Bound resource metadata tolerates that difference deliberately -- a
    workspace root is not a credential, and platform should not decide whether
    an action is refused."""
    assert _action_payload_secret_findings({"workspace_root": tmp_path_value}) == ()


def test_a_git_sha_is_not_mistaken_for_an_aws_key() -> None:
    """A 40-char hex sha matches the AWS 40-char character class, so this
    would refuse every rollback if the AWS pattern were not context-gated."""
    assert _action_payload_secret_findings({"snapshot_id": _GIT_SHA}) == ()


# --------------------------------------------------------------------------- #
# Real credentials are still refused, and now say why
# --------------------------------------------------------------------------- #


def test_a_secret_in_action_content_is_refused_and_named() -> None:
    findings = _action_payload_secret_findings(
        {"command": "export KEY=sk-abcdefghij1234567890ABCDEFGHIJ1234"}
    )

    assert findings, "a real credential must still be refused"
    assert any("OPENAI_API_KEY" in f for f in findings)
    assert any(f.startswith("payload:") for f in findings)


def test_a_named_credential_is_refused_even_in_bound_metadata() -> None:
    """Tolerance covers HIGH_ENTROPY only. A field that is allowed to be
    high-entropy is not thereby allowed to contain an actual access key."""
    findings = _action_payload_secret_findings(
        {"path": "/workspace/AKIAIOSFODNN7EXAMPLE/out"}
    )

    assert findings
    assert any(f.startswith("path:") for f in findings), (
        "the refusal must name the offending FIELD, not just the detector"
    )
    assert any("AWS_ACCESS_KEY" in f for f in findings)


def test_findings_never_include_the_offending_value() -> None:
    """The value is the thing suspected of being a secret; it must not be
    echoed into an error message, a log, or an HTTP response."""
    secret = "sk-abcdefghij1234567890ABCDEFGHIJ1234"

    findings = _action_payload_secret_findings({"command": f"export KEY={secret}"})

    assert findings
    assert all(secret not in finding for finding in findings)


# --------------------------------------------------------------------------- #
# The boolean predicate keeps its contract
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "payload",
    [
        {"mission_id": "m", "snapshot_id": _GIT_SHA},
        {"workspace_root": _MACOS_TMP},
        {"command": "export KEY=sk-abcdefghij1234567890ABCDEFGHIJ1234"},
        {"path": "/workspace/AKIAIOSFODNN7EXAMPLE/out"},
    ],
)
def test_the_predicate_agrees_with_the_findings(payload: dict) -> None:
    assert _action_payload_contains_secret(payload) == bool(
        _action_payload_secret_findings(payload)
    )
