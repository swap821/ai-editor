"""Importing the package must not provision databases.

Inventory item 5b. `import aios.policy` used to CREATE four SQLite files --
capabilities, approvals, sessions, privacy audits -- wherever the importing
process happened to point `AIOS_DATA_DIR`. The chain was:

    aios/policy/__init__.py
      -> aios/interfaces/http/edge_security.py:21
         -> from aios.api.deps import get_session_manager
            -> deps.py module body constructed four DB-backed singletons,
               each of which initialises its schema on construction

That is not merely untidy. It took the release-authority job down: two pure
static-analysis gates (`tools/thesis_audit.py`, `scripts/check_frozen_core.py`)
imported the package as the RUNNER uid, and the executor topology later in the
SAME job runs as a different uid, which then could not write the files. Three
blocking gates reported `attempt to write a readonly database` --
`operator_identity`, `mutation_authority`, `emergency_stop_controller`.

Measured at the time, against an empty data dir:

    scripts/verify_organ_contracts.py  -> 2 entries, both directories
    scripts/build_organ_ledger_doc.py  -> 0 entries
    tools/thesis_audit.py              -> 7 databases
    scripts/check_frozen_core.py       -> 4 databases

The pre-existing gates created only directories, which is why it had never bitten
before.

## What this file does and does not assert

It asserts that importing a module does not create a database. It does NOT
assert that nothing ever does: `aios.api.main` builds the FastAPI app at module
level, and constructing the application's runtime is what that import MEANS.
The line is between "I imported a library" and "I started the app".

Each case runs in a SUBPROCESS with its own `AIOS_DATA_DIR`, because import side
effects happen once per interpreter -- an in-process test would pass simply
because the current session already imported everything.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Modules a tool, gate, lint or script may import WITHOUT provisioning storage.
IMPORT_MUST_BE_CLEAN = [
    "aios",
    "aios.config",
    "aios.policy",
    "aios.policy.constitution",
    "aios.api.deps",
    "aios.api.routes.system",
    "aios.interfaces.http.edge_security",
    "aios.security.scope_lock",
    "aios.security.limits",
]


def _databases_created_by(code: str, tmp_path: Path, label: str) -> list[str]:
    data_dir = tmp_path / label
    data_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "AIOS_DATA_DIR": str(data_dir)}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"{label} failed to run: {(result.stderr or result.stdout)[-800:]}"
    )
    return sorted(p.name for p in data_dir.glob("*.db"))


@pytest.mark.parametrize("module", IMPORT_MUST_BE_CLEAN)
def test_importing_a_module_creates_no_database(module: str, tmp_path: Path) -> None:
    created = _databases_created_by(
        f"import {module}", tmp_path, module.replace(".", "_")
    )
    assert created == [], (
        f"importing {module} provisioned {created}. A module that creates storage "
        "on import provisions databases wherever it happens to run, with whatever "
        "ownership the invoking user has -- and the failure surfaces far from the "
        "cause, reading like a permissions bug in the product. Construct on first "
        "use instead; see _lazy_singleton in aios/api/deps.py."
    )


def test_the_static_analysis_gates_provision_nothing(tmp_path: Path) -> None:
    """The two gates whose import side effects actually broke CI.

    `check_frozen_core.py` also redirects AIOS_DATA_DIR itself via `setdefault`,
    but that belt is not what is under test here: an EXPLICIT AIOS_DATA_DIR wins,
    so this measures the real footprint.
    """
    created = _databases_created_by(
        "import runpy, sys; sys.argv=['check_frozen_core.py','--base','HEAD']; "
        "runpy.run_path('scripts/check_frozen_core.py', run_name='__main__')",
        tmp_path,
        "frozen_gate",
    )
    assert created == [], f"the frozen-core gate provisioned {created}"


def test_the_lazy_singletons_are_still_reachable_as_module_attributes() -> None:
    """The compatibility surface four test modules depend on.

    `deps._CAPABILITIES` and friends are reached directly to install fakes. A
    lazy rewrite that turned them into `None` would have broken that for no
    reason, so module `__getattr__` (PEP 562) builds them on attribute access.
    """
    import aios.api.deps as deps

    assert deps._CAPABILITIES is not None
    assert deps._RATE_LIMITER is not None
    assert deps._SESSION_MANAGER is not None
    assert deps._PRIVACY_AUDIT_TRACKER is not None


def test_the_singletons_are_singletons() -> None:
    """Laziness must not turn one shared object into a new one per call.

    These carry live state -- a rate limiter's per-session counts, the session
    store, the capability authority's emergency-stop wiring. Handing out a fresh
    instance per call would silently reset the very state they exist to hold.
    """
    import aios.api.deps as deps

    assert deps._capabilities() is deps._capabilities()
    assert deps._rate_limiter() is deps._rate_limiter()
    assert deps._session_manager() is deps._session_manager()
    assert deps._privacy_audit_tracker() is deps._privacy_audit_tracker()
    # And the attribute surface must return that SAME object, not a parallel one.
    assert deps._CAPABILITIES is deps._capabilities()
    assert deps.get_session_manager() is deps._session_manager()


def test_an_assigned_module_global_overrides_the_lazy_singleton() -> None:
    """Reads AND writes must both work, not just reads.

    The first version of this fix honoured `deps._SESSION_MANAGER` for reading
    (via PEP 562 `__getattr__`) but not for writing. `monkeypatch.setattr(deps,
    "_SESSION_MANAGER", fake)` sets a REAL module attribute, and `__getattr__`
    fires only when normal lookup fails -- so the accessor never saw the
    override and kept returning the production object.

    That is not a cosmetic gap: `test_human_sovereign_identity.py` installs its
    own session manager exactly this way, so every auth call ran against the
    production store and returned 403 instead of 200. CI caught it on all three
    platforms; this pins it.
    """
    import aios.api.deps as deps

    sentinel = object()
    original = deps._SESSION_MANAGER  # builds it, so teardown restores a real one
    try:
        deps._SESSION_MANAGER = sentinel  # type: ignore[assignment]
        assert deps._session_manager() is sentinel
        assert deps.get_session_manager() is sentinel
    finally:
        deps._SESSION_MANAGER = original  # type: ignore[assignment]

    assert deps._session_manager() is original


def test_an_unknown_attribute_still_raises_attribute_error() -> None:
    """`__getattr__` must not turn every typo into a silent None."""
    import aios.api.deps as deps

    with pytest.raises(AttributeError):
        deps._NO_SUCH_SINGLETON
