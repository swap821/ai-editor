"""The driver's approval allowlist: what it admits, and what it must still refuse.

`-v` was added 2026-08-18 by operator decision. A golden cohort on
gemini-3.7-flash scored 1/5 where FOUR of five failures were this regex refusing
`pytest -v training_ground/<file>.py`. The model was doing the right thing --
running the tests it had just written -- so a model that prefers `-v` measured
2.7x worse than one that prefers `-q`. That measured the regex, not the system.

Widening an approval gate is the move organ 44's plan explicitly forbids ("No
weakening the verifier, the [VERIFY] verdicts, or ALLOWED_FILE_RE /
ALLOWED_CMD_RE"), because it is how a score gets raised without a system
improving. It was done here only as an operator decision, and only as the
smallest possible change: `-v` alters pytest output verbosity and nothing else.

So this file is written refusal-first. The permissions are the easy half; the
point is that everything the old pattern refused, the new one still refuses.
"""
from __future__ import annotations

import pytest

from aios.probe_common import ALLOWED_CMD_RE, ALLOWED_FILE_RE


# ── what must still be refused ───────────────────────────────────────────────

REFUSED = [
    ("a second command chained on", "pytest -v training_ground/x.py; rm -rf /"),
    ("a piped command", "pytest -v training_ground/x.py | tee /tmp/out"),
    ("a path outside the sandbox", "pytest -v /etc/passwd"),
    ("traversal out of the sandbox", "pytest -v ../../etc/passwd"),
    ("an absolute windows path", r"pytest -v C:\Windows\System32\x.py"),
    ("a package install", "pip install evil"),
    ("a shell", "bash -c 'pytest -v training_ground/x.py'"),
    ("a different binary", "python training_ground/x.py"),
    ("a flag that takes a value", "pytest --tb=long training_ground/x.py"),
    ("test selection by keyword", "pytest -k secret training_ground/x.py"),
    ("collect-only, not widened", "pytest -v --collect-only training_ground/x.py"),
    ("doubled verbosity", "pytest -vv training_ground/x.py"),
    ("two files", "pytest -v training_ground/a.py training_ground/b.py"),
    ("a directory rather than a file", "pytest -v training_ground/"),
    ("the whole suite", "pytest -v tests/"),
    ("an env prefix", "AIOS_X=1 pytest -v training_ground/x.py"),
]


@pytest.mark.parametrize("why,command", REFUSED, ids=[c[0] for c in REFUSED])
def test_still_refused(why: str, command: str) -> None:
    assert not ALLOWED_CMD_RE.match(command), (
        f"the allowlist now admits {command!r} ({why}). Adding -v was meant to "
        "change output verbosity, not to widen what can execute."
    )


# ── what the widening was for ────────────────────────────────────────────────

PERMITTED = [
    "pytest -v training_ground/test_calculator.py",
    "pytest training_ground/test_calculator.py -v",
    "python -m pytest -v training_ground/x.py",
    'pytest -v "training_ground/x.py"',
    "pytest -v lab/x.py",
]


@pytest.mark.parametrize("command", PERMITTED)
def test_verbose_pytest_on_one_sandbox_file_is_allowed(command: str) -> None:
    assert ALLOWED_CMD_RE.match(command), (
        f"{command!r} is the shape gemini-3.7-flash actually emits; refusing it "
        "measures the regex rather than the model"
    )


def test_the_quiet_forms_still_work() -> None:
    """The widening must not cost the behaviour it replaced."""
    for command in (
        "pytest -q training_ground/x.py",
        "pytest training_ground/x.py -q",
        "python -m pytest training_ground/x.py",
        "pytest",
    ):
        assert ALLOWED_CMD_RE.match(command), command


def test_only_verbosity_flags_are_admitted() -> None:
    """Any single-letter flag other than q/v must still be refused.

    A regex written as `-[a-z]` instead of `-[qv]` would pass every test above
    and quietly admit -x, -s, -p and the rest.
    """
    import string

    for letter in string.ascii_lowercase:
        command = f"pytest -{letter} training_ground/x.py"
        allowed = bool(ALLOWED_CMD_RE.match(command))
        assert allowed == (letter in {"q", "v"}), (
            f"-{letter} allowed={allowed}; only -q and -v may be admitted"
        )


def test_the_file_allowlist_was_not_touched() -> None:
    """This change is about commands. The write gate must be unchanged."""
    assert ALLOWED_FILE_RE.match("training_ground/x.py")
    assert not ALLOWED_FILE_RE.match("aios/security/gateway.py")
    assert not ALLOWED_FILE_RE.match("training_ground/../aios/x.py")
