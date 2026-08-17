"""Memory stability is advertised, so it has to be measured — or say it wasn't.

Two defects, and the second was the worse one.

1. `get_process_memory_mb` used `resource`, which does not exist on Windows —
   the operator's platform. The first real endurance run recorded
   `memory_mb: None` on all 18 turns and said nothing about it. "Memory
   stability (no OOM / leak under sustained load)" is one of the four things
   this harness claims to validate, and a metric that reports None forever
   looks like data until somebody checks.

2. Even where `resource` exists, it read `RUSAGE_SELF` — the memory of the TEST
   DRIVER, not of GAGOS. A green memory-stability result from that would have
   measured the wrong process entirely. That is worse than measuring nothing,
   because the number would have looked real.

A third, quieter one: the per-turn sample was written to the turn record and
then discarded, so no run could report growth or a peak even when sampling
worked. The claim had nothing behind it either way.

What this file pins
-------------------
That the sampler targets the SERVER, that an unavailable measurement is stated
rather than emitted as a null, and that a present measurement is not reported
as missing.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from tools import endurance_tester


def _code_without_docstring(func) -> str:
    """Return a function's source with its docstring removed.

    The docstrings here deliberately NAME the defect they fixed, so a plain
    substring search over `inspect.getsource` matches the explanation and fails
    against correct code. Examine what runs, not what is written about it.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    fn = tree.body[0]
    body = fn.body[1:] if ast.get_docstring(fn) is not None else fn.body
    return "\n".join(ast.unparse(node) for node in body)


def test_the_sampler_targets_the_server_not_the_driver() -> None:
    """RUSAGE_SELF measured the harness. The harness is not under test.

    Pinned because the failure is silent and plausible: a driver sampling
    itself returns a real-looking number forever, and nothing downstream can
    tell it apart from the server's.
    """
    code = _code_without_docstring(endurance_tester.get_process_memory_mb)
    assert "RUSAGE_SELF" not in code, (
        "the sampler is reading the test driver's own memory again; a green "
        "memory-stability result would describe the wrong process"
    )
    assert "LISTEN" in code and "port" in code, (
        "the sampler no longer resolves the process serving the API port"
    )


def test_an_unavailable_measurement_states_a_reason() -> None:
    """None must never be silent.

    The original returned a bare None on every turn. Downstream that is
    indistinguishable from "measured, nothing to report".
    """
    import tools.endurance_tester as mod

    original = mod._MEMORY_UNAVAILABLE_REASON
    try:
        mod._MEMORY_UNAVAILABLE_REASON = None
        # Point the sampler at a port nothing serves.
        saved_base = mod.BASE
        mod.BASE = "http://127.0.0.1:1"
        try:
            value = mod.get_process_memory_mb()
        finally:
            mod.BASE = saved_base
        assert value is None
        assert mod._MEMORY_UNAVAILABLE_REASON, (
            "sampling failed and recorded no reason -- the run would emit "
            "nulls and imply the measurement was taken"
        )
        # The PROPERTY is that a reason is stated, not that it is worded a
        # particular way. The first version of this assertion demanded "port"
        # or "psutil" and failed on macOS CI, where psutil.net_connections
        # needs elevated privileges and the sampler correctly recorded
        # "AccessDenied: (pid=14447)" -- a better reason than either word I had
        # anticipated. Pinning prose instead of behaviour makes a passing
        # implementation look broken.
        reason = mod._MEMORY_UNAVAILABLE_REASON
        assert len(reason) > 8 and reason != "unknown", (
            f"the recorded reason is not informative enough to act on: {reason!r}"
        )
    finally:
        mod._MEMORY_UNAVAILABLE_REASON = original


def test_the_summary_reports_growth_when_samples_exist() -> None:
    """A measurement that is taken must reach the summary.

    The per-turn value used to be written to the turn record and discarded, so
    "no leak under sustained load" was never actually computed from anything.
    """
    source = _code_without_docstring(endurance_tester.cmd_run)
    assert "memory_readings" in source, "per-turn samples are discarded again"
    for field in (
        "memory_mb_first",
        "memory_mb_last",
        "memory_mb_peak",
        "memory_growth_mb",
    ):
        assert field in source, f"the summary no longer reports {field}"


def test_the_summary_says_so_when_memory_was_not_measured() -> None:
    """The honest branch: absent is reported as absent, not omitted."""
    source = _code_without_docstring(endurance_tester.cmd_run)
    assert "memory_unavailable" in source
    assert "NOT MEASURED" in source, (
        "an unmeasured metric prints nothing, so a reader sees a green run "
        "with no indication that a quarter of its claim was never checked"
    )
