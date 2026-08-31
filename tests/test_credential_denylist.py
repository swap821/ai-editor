"""Credential-shaped paths are refused even inside an allowlisted scope root.

Inventory item 2. `scope_lock` answers containment ("is this under a declared
root?"), which is not confidentiality. The moment a scope root is widened to a
real project -- what Phase B/F autonomy requires -- a `.env`, a `.git/config`
holding a push token, or an `.aws/credentials` inside that root was fully
readable and writable.

A partial list existed (`agent_bridge._SECRET_MARKERS`), consulted at ONE call
site, for reads only. Measured before this change:

    .env                  caught      .ssh/config            MISSED
    ~/.ssh/id_rsa         caught      .aws/credentials       MISSED
    secrets.pem           caught      .git/config            MISSED
                                      .docker/config.json    MISSED
                                      .claude/settings.json  MISSED
                                      .netrc                 MISSED

The cause was structural: it matched substrings against the BASENAME only, so
every credential store that identifies itself by its *directory* was invisible.
`.aws/credentials` is not a filename problem.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aios.policy.credential_paths import is_credential_path

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# The predicate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.production",
        "training_ground/.env",
        "~/.ssh/id_rsa",
        ".ssh/config",
        ".aws/credentials",
        ".git/config",
        ".git-credentials",
        ".docker/config.json",
        ".kube/config",
        ".gnupg/secring.gpg",
        ".claude/settings.json",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "secrets.pem",
        "server.key",
        "cert.p12",
        "lab/deploy/id_ed25519",
        "training_ground/secrets/anything.txt",
    ],
)
def test_credential_shaped_paths_are_refused(path: str) -> None:
    assert is_credential_path(path) is True, f"{path!r} slipped through"


@pytest.mark.parametrize(
    "path",
    [
        "training_ground/app.py",
        "aios/config.py",
        "README.md",
        "lab/notes.txt",
        "frontend/src/main.tsx",
        "docs/architecture/GAGOS_54_ORGANS.md",
        "environment.py",
        "keyboard.py",
        "training_ground/test_greeter.py",
    ],
)
def test_ordinary_source_is_not_refused(path: str) -> None:
    """A denylist that blocks real work gets switched off, so this matters.

    `environment.py` and `keyboard.py` are the specific near-misses: a naive
    substring rule on ".env" and ".key" refuses both.
    """
    assert is_credential_path(path) is False, f"{path!r} was refused but is ordinary"


def test_the_match_is_case_insensitive() -> None:
    """On Windows `.ENV` and `.env` are one file; a case-sensitive rule is a bypass."""
    assert is_credential_path(".ENV") is True
    assert is_credential_path("TRAINING_GROUND/.SSH/ID_RSA") is True


def test_backslash_paths_are_normalized() -> None:
    """Windows separators must not defeat the segment check."""
    assert is_credential_path(r"training_ground\.aws\credentials") is True


# --------------------------------------------------------------------------- #
# The structural rule: no chokepoint may be left unguarded
# --------------------------------------------------------------------------- #
#: Every non-frozen module that asks `scope_lock` whether a path is in scope.
#: `aios/security/*` is excluded because it is FROZEN CORE (AGENTS.md §VIII) --
#: see the module docstring of `aios/policy/credential_paths.py`.
_CHOKEPOINT_FILES = (
    "aios/agents/tool_handlers.py",
    "aios/api/routes/files.py",
    "aios/application/agent_bridge.py",
)


def test_every_scope_checking_module_also_checks_credentials() -> None:
    """Catch the NEXT unguarded chokepoint, not just today's.

    The original gap was not a missing pattern -- it was that only one of six
    places asked the question at all. A denylist wired into five of six sites is
    a denylist with a bypass, and nothing about the passing tests for those five
    would reveal it.

    So this asserts the invariant directly: any module that consults
    `is_path_in_scope` must also consult `is_credential_path`.
    """
    offenders = []
    for rel in _CHOKEPOINT_FILES:
        source = (REPO_ROOT / rel).read_text(encoding="utf-8")
        if "is_path_in_scope" in source and "is_credential_path" not in source:
            offenders.append(rel)
    assert not offenders, (
        f"these modules gate on scope but not on credentials: {offenders} -- "
        "an in-scope .env is readable through them"
    )


def test_no_new_scope_checking_module_escaped_the_list() -> None:
    """The list above must not silently fall behind the codebase.

    A module added tomorrow that calls `is_path_in_scope` would satisfy the test
    above trivially by not being in `_CHOKEPOINT_FILES`. This finds it.
    """
    found: set[str] = set()
    for path in (REPO_ROOT / "aios").rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith("aios/security/"):
            continue  # frozen core; cannot be wired without §VIII
        if "is_path_in_scope" in path.read_text(encoding="utf-8"):
            found.add(rel)

    unknown = found - set(_CHOKEPOINT_FILES)
    assert not unknown, (
        f"new scope-checking module(s) not covered by the credential denylist: "
        f"{sorted(unknown)} -- add them to _CHOKEPOINT_FILES and wire the guard"
    )


def test_the_legacy_predicate_delegates_rather_than_disagreeing() -> None:
    """`looks_secret_bearing` must not keep its own weaker answer.

    It was the only caller of the old basename-only list, so its disagreement
    with everything else was invisible. Pinned by behaviour on a case the old
    implementation got wrong.
    """
    from aios.application.agent_bridge import looks_secret_bearing

    assert looks_secret_bearing(".aws/credentials") is True, (
        "agent_bridge is back on a basename-only rule; directory-based "
        "credential stores are invisible to it again"
    )


def test_the_denylist_module_is_not_in_the_frozen_core() -> None:
    """It lives in `aios/policy/`, deliberately.

    Placing it under `aios/security/` would put it inside the frozen prefix, so
    every future addition -- a new cloud provider's credential directory -- would
    require §VIII ceremony. A list that must grow does not belong behind a freeze.
    """
    from aios.policy import credential_paths
    from aios.policy.constitution import FROZEN_PATH_PREFIXES

    rel = Path(credential_paths.__file__).resolve().relative_to(REPO_ROOT).as_posix()
    assert not any(rel.startswith(p.rstrip("/") + "/") for p in FROZEN_PATH_PREFIXES), (
        f"{rel} sits inside the frozen core; growing the denylist would require "
        "§VIII ceremony for every new credential directory"
    )


def test_the_guard_runs_before_the_file_is_opened() -> None:
    """Refuse by NAME, before any read.

    Reading then redacting is a content heuristic, and `privacy_filter` shipped a
    live AWS-key bypass built on exactly that kind of shape reasoning. A name is
    a fact. Asserted structurally because the failure -- bytes briefly in memory
    -- leaves no observable trace to assert on.
    """
    source = (REPO_ROOT / "aios/agents/tool_handlers.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "read_file"
    )

    def _line_of(predicate) -> int | None:
        for node in ast.walk(func):
            if predicate(node):
                return node.lineno
        return None

    guard_line = _line_of(
        lambda n: isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "is_credential_path"
    )
    read_line = _line_of(
        lambda n: isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "read_text"
    )
    assert guard_line is not None, "read_file no longer checks is_credential_path"
    assert read_line is not None, "read_file no longer reads -- update this test"
    assert guard_line < read_line, (
        "the credential check moved AFTER the read; the file is opened before it "
        "is refused"
    )
