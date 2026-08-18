"""One-time enrollment material must reach the operator, or nobody.

Organ 44 blocker 4: the enrollment credential is one-time, the driver received
it, used it, and then discarded it -- so every instance was single-use. The
second run gets a 409 and `ProbeSession.bootstrap` correctly refuses to invent
one. That made the endurance harness, which needs repeated runs to measure
anything at all, unrunnable without throwing the instance away each time.

The fix may not persist it. AGENTS.md VII.4: "Keys live only in volatile env
vars; never on disk, in logs, or in `.aios/`." So the credential is printed
once, to a terminal, and nowhere else -- the same guard
`scripts/spine_release_attest.py::cmd_sign` puts on the signing key, for the
same reason: an agent session, a CI job, and a `> run.log` redirect are
indistinguishable from inside the process.
"""
from __future__ import annotations

import contextlib
import io


from aios.probe_session import surface_enrollment_credential

SECRET = "one-time-enrollment-credential-DO-NOT-LEAK"


def _capture(isatty: bool, monkeypatch):
    out, err = io.StringIO(), io.StringIO()
    out.isatty = lambda: isatty  # type: ignore[method-assign]
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        shown = surface_enrollment_credential(SECRET, "operator-1")
    return shown, out.getvalue(), err.getvalue()


def test_a_captured_stdout_never_sees_the_credential(monkeypatch) -> None:
    """The case that matters: an agent or CI run must not capture the secret."""
    shown, out, err = _capture(False, monkeypatch)

    assert shown is False
    assert SECRET not in out, "credential leaked into captured stdout"
    assert SECRET not in err, "credential leaked into captured stderr"


def test_the_refusal_says_how_to_proceed(monkeypatch) -> None:
    """A refusal with no way forward is the dead end this repo keeps fixing."""
    _, _, err = _capture(False, monkeypatch)

    assert "AIOS_OPERATOR_CREDENTIAL" in err, "no volatile-env route offered"
    assert "AIOS_DATA_DIR" in err, "no fresh-instance route offered"


def test_a_terminal_gets_the_credential_once(monkeypatch) -> None:
    """A human at a terminal is the only audience allowed to see it."""
    shown, out, err = _capture(True, monkeypatch)

    assert shown is True
    assert SECRET in out
    assert "AIOS_OPERATOR_CREDENTIAL" in out, "shown without telling them what it is for"


def test_nothing_is_written_to_disk(tmp_path, monkeypatch) -> None:
    """VII.4 is absolute: never on disk, in logs, or in .aios/.

    Runs the surfacing path with the working directory inside tmp_path and
    asserts it created nothing at all.
    """
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.rglob("*"))

    out = io.StringIO()
    out.isatty = lambda: True  # type: ignore[method-assign]
    with contextlib.redirect_stdout(out):
        surface_enrollment_credential(SECRET, "operator-1")

    assert set(tmp_path.rglob("*")) == before, "surfacing the credential wrote a file"


def test_the_source_never_opens_a_file(monkeypatch) -> None:
    """Structural: no future 'convenience' persistence.

    Asserted against the code because a behavioural test only covers the paths
    it happens to walk, and VII.4 is not a path-dependent rule.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(surface_enrollment_credential)))
    body = ast.unparse(tree)
    for forbidden in ("open(", "write_text", "Path(", "os.makedirs", "mkdir"):
        assert forbidden not in body, (
            f"surface_enrollment_credential references {forbidden!r}; one-time "
            "credentials may never be persisted (AGENTS.md VII.4)"
        )


def test_the_message_is_actually_readable(monkeypatch) -> None:
    """The refusal must contain real newlines, not two literal characters.

    The first version of this helper was generated with an escaped separator
    and printed one long line ending in backslash-n sequences. Every assertion
    above still passed -- they check for substrings, and substrings survive a
    broken separator. A message nobody can read is not guidance.

    The needle is built with chr() so that no amount of quoting between here
    and the file can turn it back into a real newline -- which is exactly how
    the first attempt at this test managed to assert nothing.
    """
    _, _, err = _capture(False, monkeypatch)

    literal_backslash_n = chr(92) + "n"
    assert literal_backslash_n not in err, (
        "literal backslash-n in the operator-facing message"
    )
    assert len(err.strip().splitlines()) >= 5, "the guidance collapsed onto one line"
