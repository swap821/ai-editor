"""GAGOS rings the doorbell: its brief through the health watch's notification.

2026-11-24, the operator's choice: ring once for each thing that BROKE and once
when something NEW starts waiting on him; a wait that stands never rings
twice, one that ends and comes back rings again. Pinned here, and that the
doorbell reads the brief through the face's own providers and the brief's own
wording, so the two cannot drift apart.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from aios.application.observability import brief as gagos_brief
from tools import health_watch as hw

PR_752 = "GAGOS's pull request #752 is not yet seen merged."
PR_753 = "GAGOS's pull request #753 is not yet seen merged."
NO_ENVELOPE = (
    "No mission envelope is live (expired), so GAGOS starts no council missions."
)


def _cycle(tmp_path: Path, told):
    shown: list[tuple[str, str]] = []
    read = told if callable(told) else (lambda: told)
    report = hw.run_once(
        data_dir=tmp_path,
        notify=lambda t, b: shown.append((t, b)) or True,
        ollama_check=lambda: ({"available": True}, []),
        ci_runs=lambda: [],
        brief=read,
    )
    return report, shown


def test_it_rings_once_for_what_broke_and_what_newly_waits(tmp_path: Path) -> None:
    told = {
        "broke": ["Hour 2026-11-24T09 was failed: no plan brain."],
        "waiting": [PR_752],
    }
    report, shown = _cycle(tmp_path, told)
    assert [t for t, _ in shown] == ["GAGOS: something broke", "GAGOS: waiting on you"]
    assert "no plan brain" in shown[0][1] and "#752" in shown[1][1]
    assert report.brief == {"read": True, "broke": 1, "waiting": 1, "new": 2}

    _, shown = _cycle(tmp_path, told)
    assert shown == [], "a standing wait or break rang twice"


def test_a_new_pull_request_rings_though_another_already_waits(tmp_path: Path) -> None:
    _cycle(tmp_path, {"waiting": [PR_752]})
    _, shown = _cycle(tmp_path, {"waiting": [PR_752, PR_753]})
    assert shown == [("GAGOS: waiting on you", PR_753)]


def test_a_wait_that_ends_and_comes_back_rings_again(tmp_path: Path) -> None:
    _cycle(tmp_path, {"waiting": [NO_ENVELOPE]})
    _, shown = _cycle(tmp_path, {"waiting": []})
    assert shown == []
    _, shown = _cycle(tmp_path, {"waiting": [NO_ENVELOPE]})
    assert shown == [("GAGOS: waiting on you", NO_ENVELOPE)]


def test_a_long_list_shows_three_lines_and_counts_the_rest(tmp_path: Path) -> None:
    waits = [
        f"GAGOS's pull request #{n} is not yet seen merged." for n in range(760, 765)
    ]
    _, shown = _cycle(tmp_path, {"waiting": waits})
    assert shown[0][1].splitlines() == [*waits[:3], "(and 2 more)"]


def test_an_unreadable_brief_rings_once_per_cause(tmp_path: Path) -> None:
    def broken():
        raise RuntimeError("ledger is locked")

    report, shown = _cycle(tmp_path, broken)
    assert shown == [
        ("GAGOS's brief could not be read", "RuntimeError: ledger is locked")
    ]
    assert report.brief["read"] is False
    _, shown = _cycle(tmp_path, broken)
    assert shown == []


def test_a_silence_that_lasts_rings_once_in_the_briefs_own_words(
    tmp_path: Path,
) -> None:
    """The brief's silence line carries a running count; the doorbell keys it
    without that count, read from compose() itself, not a copy of its words."""
    last = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
    hour = {
        "day": "2026-11-24T02",
        "status": "ran",
        "reason": "",
        "updated_at": last.isoformat(),
    }

    def told(hours_later: int) -> dict:
        now = last + timedelta(hours=hours_later)
        facts = gagos_brief.Facts(
            since=now - timedelta(hours=24),
            now=now,
            hours=(hour,),
            mission_envelope={"live": True},
        )
        return gagos_brief.compose(facts).as_dict()

    four, five = told(4), told(5)
    assert four["broke"] != five["broke"], (
        "the count did not run; the test proves nothing"
    )
    _, shown = _cycle(tmp_path, four)
    assert [t for t, _ in shown] == ["GAGOS: something broke"]
    _, shown = _cycle(tmp_path, five)
    assert shown == [], "the same silence rang again an hour later"


def test_the_doorbell_reads_the_brief_through_the_faces_providers(monkeypatch) -> None:
    """One derivation, two callers: what the face's brief route reads is what
    the doorbell reads (its ledger, envelopes, organ ledger, stop)."""
    from aios.api.routes import gagos_tasks as route

    class _Ledger:
        path = Path("from-the-route.db")

    class _Envelope:
        def __init__(self, live: bool) -> None:
            self._live = live

        def status(self) -> dict:
            return {"live": self._live}

    monkeypatch.setattr(route, "get_gagos_task_ledger", lambda: _Ledger())
    monkeypatch.setattr(route, "get_gagos_envelope_authority", lambda: _Envelope(True))
    monkeypatch.setattr(
        route, "get_gagos_skill_envelope_authority", lambda: _Envelope(False)
    )
    monkeypatch.setattr(
        route, "get_organ_ledger_path", lambda: Path("organs-from-the-route.json")
    )
    monkeypatch.setattr(route, "_stop_engaged", lambda: True)
    seen: dict = {}

    def gather(**kwargs):
        seen.update(kwargs)
        return gagos_brief.Brief(since="s", now="n", broke=("stop",))

    monkeypatch.setattr(gagos_brief, "gather", gather)
    assert hw.gagos_brief()["broke"] == ["stop"]
    assert seen["ledger_db"] == Path("from-the-route.db")
    assert seen["organ_ledger_path"] == Path("organs-from-the-route.json")
    assert seen["mission_envelope"] == {"live": True}
    assert seen["skill_envelope"] == {"live": False}
    assert seen["stop_engaged"] is True
    assert seen["now"] - seen["since"] == route.BRIEF_FIRST_LOOK
