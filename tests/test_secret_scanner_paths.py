"""Filesystem paths are not credentials — and secrets inside them still are.

The defect
----------
`scan_and_redact` runs three passes. Pass 3 (sliding-window) requires
`_has_secret_context` before redacting. **Pass 2 has no context gate and no
false-positive guard at all** — it redacts on length plus entropy alone. `/` is
in the base64 alphabet, so a long unix path is indistinguishable from an
encoded blob by entropy:

    token   '/workspace/jobs/training_ground/test_calculator'
    len 47  entropy 4.145  threshold 4.0  -> REDACTED

That string appears inside pytest's own message:

    ImportError while importing test module '<REDACTED:HIGH_ENTROPY:...>.py'

So an agent reading its test output was told an import failed and never told
WHICH module. Organ 44's golden cohort lost a mission to it — the agent could
not fix what it could not see. `aios/memory/skills.py:161` already carried a
local workaround comment for the same shape, which is how a false positive
announces it has been around a while.

Why the fix cannot hide a secret
--------------------------------
`_is_filesystem_path` checks every segment INDEPENDENTLY against the same
credential test the caller applies to whole tokens, so a key embedded in a path
keeps its redaction. Only the aggregate path is exempt, and only when every one
of its parts is individually innocuous. Base64-only characters (`+`, `=`) are
excluded from a valid segment, so a padded blob containing `/` cannot pose as
a path.

This file exists because that claim needs to be enforced rather than asserted.
The MUST_REDACT half is the half that matters: a false-positive fix that let a
real credential through would be far worse than the bug it fixed. This code is
inside the frozen security spine (`aios/security/`) and reached master through
a §VIII controlled release.
"""

from __future__ import annotations

import pytest

from aios.security.secret_scanner import scan_and_redact

_BACKSLASH = chr(92)

MUST_REDACT = {
    "aws key inside a path": "/tmp/AKIAIOSFODNN7EXAMPLE",
    "aws secret as a path segment": (
        "/home/u/.aws/wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY"
    ),
    "padded base64 blob containing slashes": (
        "Zm9vYmFy/YmF6cXV4+abcdefghijklmnop/QRSTUVWXYZ0123456789ab=="
    ),
    "openai-style key": "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGH",
    "bare high-entropy token": "aGVsbG93b3JsZDEyMzQ1Njc4OWFiY2RlZmdoaWprbG1ub3A",
    "high-entropy segment in an ordinary path": (
        "/var/lib/aGVsbG93b3JsZDEyMzQ1Njc4OWFiY2RlZmdoaWprbG0"
    ),
    "jwt": (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0"
        ".dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    ),
}

MUST_NOT_REDACT = {
    "the reported false positive": (
        "/workspace/jobs/training_ground/test_calculator.py"
    ),
    "repo-relative path": "training_ground/test_safe_json.py",
    "nested source path": "aios/application/governance/constitutional_learning.py",
    "windows path": (
        "C:" + _BACKSLASH + "Users" + _BACKSLASH + "kumar" + _BACKSLASH + "x.py"
    ),
    "the whole pytest error line": (
        "ImportError while importing test module "
        "'/workspace/jobs/training_ground/test_calculator.py'."
    ),
}


@pytest.mark.parametrize("name", sorted(MUST_REDACT))
def test_real_credentials_are_still_redacted(name: str) -> None:
    """The half that matters.

    A path exemption that let a credential through would be a far worse defect
    than the false positive it fixed, so every shape that could plausibly wear
    a path as a disguise is pinned here -- including secrets sitting in a path
    segment and padded blobs containing slashes.
    """
    result = scan_and_redact(MUST_REDACT[name])
    assert result.detected, f"{name!r} was NOT redacted: {MUST_REDACT[name]!r}"
    assert MUST_REDACT[name] not in result.scrubbed


@pytest.mark.parametrize("name", sorted(MUST_NOT_REDACT))
def test_filesystem_paths_survive_intact(name: str) -> None:
    """Paths must reach the reader unmangled.

    Asserts the text is not merely 'not detected' but byte-identical: a partial
    redaction that mangles half a path is the same failure in a smaller costume.
    """
    text = MUST_NOT_REDACT[name]
    result = scan_and_redact(text)
    assert not result.detected, f"{name!r} was redacted: {result.findings}"
    assert result.scrubbed == text


def test_a_path_whose_segment_is_a_credential_is_not_exempt() -> None:
    """The exemption is per-segment, not per-token.

    Stated as its own test because it is the property the whole fix rests on:
    wrapping a key in slashes must not launder it.
    """
    laundered = "/opt/app/config/aGVsbG93b3JsZDEyMzQ1Njc4OWFiY2RlZmdoaWprbG0"
    result = scan_and_redact(laundered)
    assert result.detected
    assert "HIGH_ENTROPY" in result.findings


def test_the_agent_can_read_which_module_failed_to_import() -> None:
    """The end-to-end symptom, in the exact shape pytest emits it.

    This is what organ 44's cohort actually hit; if it ever regresses the
    failure message names the real-world consequence rather than an entropy
    threshold.
    """
    pytest_error = (
        "==================== ERRORS ====================\n"
        "ERROR collecting training_ground/test_calculator.py\n"
        "ImportError while importing test module "
        "'/workspace/jobs/training_ground/test_calculator.py'.\n"
    )
    scrubbed = scan_and_redact(pytest_error).scrubbed
    assert "test_calculator.py" in scrubbed
    assert "REDACTED" not in scrubbed, (
        "the agent cannot fix an import error whose module name has been "
        "redacted out of the message"
    )
