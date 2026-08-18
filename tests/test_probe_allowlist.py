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
    # --tb=<style> is now admitted: it formats tracebacks and changes nothing
    # about what runs. A value-taking flag that DOES change behaviour is
    # covered by the --rootdir and -c cases below.
    ("a value flag that changes behaviour", "pytest --rootdir=/tmp training_ground/x.py"),
    ("test selection by keyword", "pytest -k secret training_ground/x.py"),
    ("plugin loading", "pytest -p evil training_ground/x.py"),
    ("bundled -s with -k", "pytest -sk sel training_ground/x.py"),
    ("-o config override", "pytest -o junit_suite_name=x training_ground/x.py"),
    ("-s does not launder -k", "pytest -s -k sel training_ground/x.py"),
    ("-s does not launder --pdb", "pytest -s --pdb training_ground/x.py"),
    ("interactive debugger", "pytest --pdb training_ground/x.py"),
    ("stop on first failure", "pytest -x training_ground/x.py"),
    ("conftest suppression", "pytest --noconftest training_ground/x.py"),
    ("a rootdir path", "pytest --rootdir=/ training_ground/x.py"),
    ("two files", "pytest -v training_ground/a.py training_ground/b.py"),
    ("a directory rather than a file", "pytest -v training_ground/"),
    ("a nested path", "pytest training_ground/subdir/foo.py"),
    ("a nested path with -v", "pytest -v training_ground/subdir/foo.py"),
    ("a nested lab path", "pytest lab/subdir/foo.py"),
    ("traversal into the source tree", "pytest training_ground/../aios/x.py"),
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
    "pytest -q --collect-only training_ground/test_pipeline.py",
    "pytest training_ground/test_sorted_insert.py -q --no-header",
    "pytest --tb=short training_ground/x.py",
    "pytest -vv training_ground/x.py",
    "pytest -s training_ground/x.py",
    "pytest -vv -s training_ground/test_pipeline.py",
    "pytest training_ground/x.py -s",
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


def test_only_the_named_short_flags_are_admitted() -> None:
    """Exactly three single-letter flags, and no others.

    q/v are verbosity; s disables output capture so print() is visible. All
    three change what is PRINTED and nothing about what runs.

    This loops the whole alphabet because a pattern that drifted to `-[a-z]`
    would pass every hand-written case in this file while admitting -x (stop on
    first failure), -k (select tests) and -p (load arbitrary plugins). It has
    already earned its keep once: it failed when -s was added, which is the
    correct behaviour for a guard on a security gate -- widening the set has to
    be a deliberate edit here, not a side effect somewhere else.
    """
    import string

    from aios.probe_common import ALLOWED_CMD_RE

    admitted = {"q", "v", "s"}
    for letter in string.ascii_lowercase:
        command = f"pytest -{letter} training_ground/x.py"
        allowed = bool(ALLOWED_CMD_RE.match(command))
        assert allowed == (letter in admitted), (
            f"-{letter} allowed={allowed}; the admitted short flags are "
            f"{sorted(admitted)} and changing that set is a security decision"
        )

def test_the_file_allowlist_was_not_touched() -> None:
    """This change is about commands. The write gate must be unchanged."""
    assert ALLOWED_FILE_RE.match("training_ground/x.py")
    assert not ALLOWED_FILE_RE.match("aios/security/gateway.py")
    assert not ALLOWED_FILE_RE.match("training_ground/../aios/x.py")


def test_only_output_flags_are_admitted() -> None:
    """Every flag that changes WHAT RUNS must still be refused.

    The widening is justified only if the admitted flags are output-only. A
    pattern that drifted to `--[a-z-]+` would pass every case above and quietly
    admit -p (arbitrary plugin loading), --pdb (interactive), or --rootdir
    (takes a path).
    """
    from aios.probe_common import ALLOWED_CMD_RE

    execution_changing = [
        "-k sel", "-x", "-p plug", "--pdb", "--noconftest", "--rootdir=/",
        "-o junit_suite_name=x", "--pdbcls=IPython:TerminalPdb",
        "-c setup.cfg", "--import-mode=importlib", "-n 4", "--lf", "--ff",
    ]
    for flag in execution_changing:
        cmd = f"pytest {flag} training_ground/x.py"
        assert not ALLOWED_CMD_RE.match(cmd), (
            f"{flag!r} changes what executes and must not be admitted by a "
            "widening justified as output-only"
        )


def test_the_pattern_is_built_from_named_parts() -> None:
    """Structural: the previous widening was one long literal and lost a
    backslash, silently admitting nested paths. Named parts make the character
    class reviewable on its own line."""
    from aios import probe_common

    assert hasattr(probe_common, "_PYTEST_READ_ONLY_FLAG")
    assert hasattr(probe_common, "_SANDBOX_TEST_FILE")
