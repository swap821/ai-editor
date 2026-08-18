"""The driver must never surface the one-time enrollment credential.

Organ 44 blocker 4: the credential is one-time, the driver received it, used it,
and discarded it -- so every instance was single-use. The second run gets a 409
and `ProbeSession.bootstrap` correctly refuses to invent one, which made the
endurance harness unrunnable without throwing the instance away each time.

The first fix printed the credential to a TTY behind an `isatty()` guard.
AGENTS.md VII.4 arguably permits that -- a terminal is not disk, not a log, not
`.aios/` -- but CodeQL flagged it high severity
(`py/clear-text-logging-sensitive-data`) and was right to: the guard is
invisible to any reader, and "we print secrets, but only sometimes" is a worse
invariant than "we never print secrets".

So the helper now takes ONLY the operator id. It cannot leak what it never
receives, which is the rule `spine_release_attest.py::cmd_keygen` states for
signing keys. The operator is told how to enroll themselves instead.
"""
from __future__ import annotations

import contextlib
import inspect
import io

from aios.probe_session import explain_reusable_enrollment


def _capture(operator_id: str | None = "operator-1") -> tuple[str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        explain_reusable_enrollment(operator_id)
    return out.getvalue(), err.getvalue()


def test_the_helper_cannot_receive_a_credential() -> None:
    """Structural, and the whole point: no parameter can carry the secret."""
    params = list(inspect.signature(explain_reusable_enrollment).parameters)

    assert params == ["operator_id"], (
        f"signature is {params}; a helper that accepts a credential can leak "
        "one. It must not be able to hold the secret at all."
    )


def test_it_explains_both_routes_to_a_repeatable_run() -> None:
    """A refusal with no way forward is the dead end this repo keeps fixing."""
    _out, err = _capture()

    assert "AIOS_OPERATOR_CREDENTIAL" in err, "no volatile-env route offered"
    assert "AIOS_DATA_DIR" in err, "no fresh-instance route offered"
    assert "/api/v1/auth/enroll" in err, "no way to obtain a reusable credential"


def test_the_guidance_goes_to_stderr_not_stdout() -> None:
    """stdout is the driver's data channel; guidance must not pollute it."""
    out, err = _capture()

    assert err.strip(), "no guidance emitted"
    assert not out.strip(), "guidance leaked into the data channel"


def test_the_message_is_readable() -> None:
    r"""Real newlines, not the two characters backslash-n.

    An earlier version of this helper was generated with an escaped separator
    and printed one long line ending in literal backslash-n sequences. Substring
    assertions all still passed, because substrings survive a broken separator.
    The needle is built with chr() so no quoting layer between here and the file
    can turn it back into a real newline -- which is exactly how the first
    attempt at this test managed to assert nothing.
    """
    _out, err = _capture()

    assert (chr(92) + "n") not in err, "literal backslash-n in operator guidance"
    assert len(err.strip().splitlines()) >= 5, "the guidance collapsed onto one line"


def test_nothing_is_written_to_disk(tmp_path, monkeypatch) -> None:
    """VII.4 is absolute: never on disk, in logs, or in .aios/."""
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.rglob("*"))

    with contextlib.redirect_stderr(io.StringIO()):
        explain_reusable_enrollment("operator-1")

    assert set(tmp_path.rglob("*")) == before, "explaining enrollment wrote a file"


def test_the_source_never_opens_a_file() -> None:
    """Structural: no future 'convenience' persistence.

    Asserted against the code because a behavioural test only covers the paths
    it happens to walk, and VII.4 is not a path-dependent rule.
    """
    import ast
    import textwrap

    body = ast.unparse(
        ast.parse(textwrap.dedent(inspect.getsource(explain_reusable_enrollment)))
    )
    for forbidden in ("open(", "write_text", "Path(", "os.makedirs", "mkdir"):
        assert forbidden not in body, (
            f"explain_reusable_enrollment references {forbidden!r}; one-time "
            "credentials may never be persisted (AGENTS.md VII.4)"
        )


def test_bootstrap_does_not_pass_the_credential_to_the_explainer() -> None:
    """The call site must not hand over what the helper refuses to take."""
    from aios.probe_session import ProbeSession

    src = inspect.getsource(ProbeSession.bootstrap)

    assert "explain_reusable_enrollment(self.operator_id)" in src
    assert "explain_reusable_enrollment(credential" not in src
