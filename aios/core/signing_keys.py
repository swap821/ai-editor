"""Whether a missing signing key may fall back to a test placeholder: one rule.

The verification, promotion, checkpoint and API-token keys each refuse to run
without a real secret, except in a test run or when the operator allows test
keys outright. Until 2026-11-09 the four modules that hold those keys each
spelled the exception out themselves, the same two lines four times; a change to
one would have left three keys judging "is this a test" another way.
"""

from __future__ import annotations

import os


def test_keys_allowed() -> bool:
    """In a test or CI run (``AIOS_ENV``), or with ``AIOS_TEST_SIGNING_KEYS_ALLOWED``."""
    return os.environ.get("AIOS_ENV", "").lower() in ("test", "testing", "ci") or bool(
        os.environ.get("AIOS_TEST_SIGNING_KEYS_ALLOWED", "")
    )


__all__ = ["test_keys_allowed"]
