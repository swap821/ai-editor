"""Phase 2 of GAGOS's browser journeys (2026-11-16, the operator's yes): he
sends, the runner watches. Pinned with a stand-in face that plays one turn:

* the runner never types or sends anything;
* one request is followed by its turn_id from the send, through the backend's
  own event ids, to its terminal event on both channels;
* a receipt must match how the turn ended;
* nothing of what he typed or what the model said is recorded.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tools import gagos_journeys as gj

TURN = "turn-7"


def _mirror(event_id: int, kind: str, turn: str = TURN) -> dict:
    return {
        "method": "Network.eventSourceMessageReceived",
        "params": {
            "eventId": str(event_id),
            "eventName": "message",
            "data": json.dumps({"eventType": kind, "payload": {"turn_id": turn}}),
        },
    }


class WatchPage:
    """A stand-in face: the operator types, sends, and the turn ends."""

    def __init__(
        self,
        *,
        signed_in=True,
        end="done",
        receipt="verified-success",
        turn_ids=(TURN,),
        mirror_end="turn.completed",
        requests=1,
    ) -> None:
        self.signed = signed_in
        self.end = end
        self.receipt = receipt
        self.turn_ids = turn_ids
        self.mirror_end = mirror_end
        self.polls = 0
        self.sent: list[dict] = []
        self.events: list[dict] = [
            {
                "method": "Network.requestWillBeSent",
                "params": {
                    "request": {
                        "method": "POST",
                        "url": "http://localhost:8000/api/generate",
                    }
                },
            }
            for _ in range(requests)
        ]

    async def send(self, method: str, **params):
        self.sent.append({"method": method, **params})
        return {}

    def _turns(self) -> list[dict]:
        if self.polls < 2:
            return []
        frames = [
            {"event": "turn.started", "bytes": 40, "turnId": tid}
            for tid in self.turn_ids
        ]
        frames.append({"event": "text_chunk", "bytes": 12, "turnId": None})
        if self.polls >= 4:
            frames.append({"event": self.end, "bytes": 30, "turnId": self.turn_ids[0]})
            if (
                not self.events
                or self.events[-1].get("params", {}).get("eventId") != "42"
            ):
                self.events += [_mirror(41, "turn.started")]
                if self.mirror_end:
                    self.events += [_mirror(42, self.mirror_end)]
        return [{"at": 1.0, "status": 200, "frames": frames}]

    async def evaluate(self, expression: str):
        if "data-controls-ready" in expression:
            return True
        if "/api/v1/auth/session" in expression:
            return self.signed
        if "__gagosBodyDraws" in expression:
            return {"draws": 2400, "frames": 60}
        if "gagos-receipt--" in expression:
            self.polls += 1
            if self.polls == 1:
                return {
                    "working": "false",
                    "phase": "rest",
                    "approval": False,
                    "receipts": [],
                    "draft": 14,
                }
            if self.polls < 4:
                return {
                    "working": "true",
                    "phase": "working",
                    "approval": False,
                    "receipts": [],
                    "draft": 0,
                }
            return {
                "working": "false",
                "phase": "rest",
                "approval": False,
                "receipts": [self.receipt] if self.receipt else [],
                "draft": 0,
            }
        if "__gagosTurns" in expression:
            return self._turns()
        if "__gagosJourney?.errors" in expression:
            return []
        if "__gagosJourney?.metrics" in expression:
            return []
        return None


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(gj.asyncio, "sleep", no_wait)


def _watch(page: WatchPage) -> gj.JourneyRecord:
    record = gj.JourneyRecord(
        journey="ask-01",
        criterion="UX-01",
        commit="a" * 40,
        browser="Chrome/157",
        viewport="as the operator has it",
        url=gj.FACE_URL,
        started_at="2026-11-16T14:00:00+00:00",
    )
    journey = gj.Journey(page, record)
    asyncio.run(gj.ask_01(journey))
    return record.finish()


def test_one_sent_turn_is_followed_to_its_end_on_both_channels(tmp_path) -> None:
    page = WatchPage()
    record = _watch(page)
    steps = {s.name: s for s in record.steps}
    assert record.outcome == "passed", [(s.name, s.ok, s.detail) for s in record.steps]
    assert steps["the backend started it"].detail == "turn.started as event 41"
    assert steps["it ended, on both channels"].detail == (
        "stream: done; mirror: turn.completed as event 42"
    )
    assert steps["an honest receipt"].detail == "shown: verified-success; after done"
    assert record.measured["frames by type"] == {
        "turn.started": 1,
        "text_chunk": 1,
        "done": 1,
    }
    text = gj.write_record(record, tmp_path).read_text(encoding="utf-8")
    assert "never their text" in text


def test_the_runner_never_types_or_sends() -> None:
    page = WatchPage()
    _watch(page)
    driven = [c["method"] for c in page.sent if c["method"].startswith("Input.")]
    assert driven == []


def test_signed_out_stops_before_watching() -> None:
    record = _watch(WatchPage(signed_in=False))
    assert [s.name for s in record.steps] == ["controls ready", "signed in"]
    assert record.outcome == "failed"


def test_a_verified_receipt_after_an_error_is_not_honest() -> None:
    record = _watch(
        WatchPage(end="error", receipt="verified-success", mirror_end="turn.failed")
    )
    steps = {s.name: s for s in record.steps}
    assert not steps["an honest receipt"].ok
    assert record.outcome == "failed"


def test_a_failure_receipt_after_an_error_is_honest() -> None:
    record = _watch(WatchPage(end="error", receipt="failure", mirror_end="turn.failed"))
    assert {s.name: s for s in record.steps}["an honest receipt"].ok


def test_the_mirror_must_end_the_turn_too() -> None:
    record = _watch(WatchPage(mirror_end=None))
    steps = {s.name: s for s in record.steps}
    assert not steps["it ended, on both channels"].ok


def test_two_requests_or_two_turns_are_not_one_journey() -> None:
    assert _watch(WatchPage(requests=2)).outcome == "failed"
    record = _watch(WatchPage(turn_ids=(TURN, "turn-8")))
    assert not {s.name: s for s in record.steps}["one turn"].ok


def test_mirror_events_keep_ids_types_and_turns_only() -> None:
    events = [
        _mirror(5, "turn.started"),
        {"method": "Network.requestWillBeSent", "params": {}},
        {
            "method": "Network.eventSourceMessageReceived",
            "params": {"eventId": "6", "data": "not json"},
        },
    ]
    assert gj.mirror_events(events) == [
        {"id": "5", "type": "turn.started", "turnId": TURN},
        {"id": "6", "type": "", "turnId": None},
    ]


def test_the_turn_probe_keeps_no_text() -> None:
    probe = gj._TURN_PROBE
    assert "bytes: raw.length" in probe and "turnId" in probe
    assert (
        "frames.push({ at: performance.now(), event, bytes: raw.length, turnId })"
        in probe
    )


def test_signed_in_asks_the_backend_not_the_faces_own_origin() -> None:
    """2026-11-16: the face's origin answers /api/v1/auth/session with its own
    page (200, text/html), so the check could never say yes."""
    assert gj.BACKEND + "/api/v1/auth/session" in json.dumps(
        gj.BACKEND + "/api/v1/auth/session"
    )
    seen = []

    class Page:
        events: list = []

        async def evaluate(self, expression):
            seen.append(expression)
            return True

    record = gj.JourneyRecord(
        journey="x",
        criterion="x",
        commit="c",
        browser="b",
        viewport="v",
        url=gj.FACE_URL,
        started_at="s",
    )
    assert asyncio.run(gj.Journey(Page(), record).signed_in()) is True
    assert json.dumps(gj.BACKEND + "/api/v1/auth/session") in seen[0]
