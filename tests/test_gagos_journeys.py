"""GAGOS's browser journeys over its face (2026-11-15, the operator's "option
1"). Pinned here with a stand-in page, no Chrome:

* the journey Chrome is GAGOS's own profile, DevTools on 127.0.0.1 only;
* the runner never presses an Allow or Approve control;
* only whether the page is signed in is kept, never the operator's id or token;
* REC-01 passes only when the draft survives, the view restores exactly once
  and no work request is sent; every record carries its boundary.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tools import gagos_journeys as gj


class Page:
    """A stand-in for the face, answering the runner's expressions."""

    def __init__(
        self,
        *,
        restores: int = 1,
        remounts: bool = False,
        fallback: bool = False,
        retry_recovers: bool = False,
        button: str = "Stop",
        events=(),
    ) -> None:
        self.remounts = remounts
        self.fallback = fallback
        self.retry_recovers = retry_recovers
        self.value = ""
        self.metrics: list[dict] = []
        self.restores = restores
        self.button = button
        self.clicked: list[str] = []
        self.events = list(events)

    async def send(self, method: str, **params):
        if method == "Input.insertText":
            self.value += params["text"]
        return {}

    async def evaluate(self, expression: str):
        if "lm-renderer-fallback-notice" in expression:
            return self.fallback
        if "lm-renderer-fallback__retry" in expression and expression.endswith(
            ".click()"
        ):
            self.clicked.append(expression)
            self.remounts = self.remounts or self.retry_recovers
            return None
        if "?.value === " in expression:
            wanted = json.loads(expression.rsplit("=== ", 1)[1].rstrip(")"))
            return self.value == wanted
        if "data-controls-ready" in expression:
            return True
        if "/api/v1/auth/session" in expression:
            return True
        if "restoreContext" in expression:
            self.metrics += [{"name": "context-recovery", "value": 40}] * self.restores
            return None
        if "WEBGL_lose_context" in expression:
            return True
        restored = any(m["name"] == "context-recovery" for m in self.metrics)
        if "c !== window.__gagosJourneyCanvas" in expression and "||" in expression:
            return restored or self.remounts  # the wait: either recovery
        if "c !== window.__gagosJourneyCanvas" in expression:
            return self.remounts
        if ".some(m => m.name === 'context-recovery')" in expression:
            return restored
        if "__gagosJourney?.metrics" in expression:
            return self.metrics
        if "__gagosJourney?.errors" in expression:
            return []
        if "?.value ?? ''" in expression:
            return self.value
        if "innerText" in expression:
            return self.button
        if expression.endswith(".click()"):
            self.clicked.append(expression)
            return None
        return None


def _journey(page: Page, tmp_path: Path) -> gj.Journey:
    record = gj.JourneyRecord(
        journey="rec-01",
        criterion="REC-01",
        commit="a" * 40,
        browser="Chrome/140",
        viewport="1280x720",
        url=gj.FACE_URL,
        started_at="2026-11-15T18:00:00+00:00",
    )
    return gj.Journey(page, record)


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(gj.asyncio, "sleep", no_wait)


def test_rec_01_passes_when_the_draft_survives_and_the_view_restores_once(
    tmp_path,
) -> None:
    page = Page()
    journey = _journey(page, tmp_path)
    asyncio.run(gj.rec_01(journey))
    record = journey.record.finish()
    assert record.outcome == "passed", [(s.name, s.ok, s.detail) for s in record.steps]
    assert record.signed_in is True
    path = gj.write_record(record, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "## Evidence boundary" in text and "earns no points" in text
    data = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["outcome"] == "passed" and data["commit"] == "a" * 40
    assert "operator_id" not in json.dumps(data) and "csrf" not in json.dumps(data)


def test_rec_01_fails_when_the_view_restores_twice(tmp_path) -> None:
    journey = _journey(Page(restores=2), tmp_path)
    asyncio.run(gj.rec_01(journey))
    record = journey.record.finish()
    (once,) = [s for s in record.steps if s.name == "recovered once"]
    assert not once.ok and once.detail == "2 in-place restore(s), 0 remount(s)"
    assert record.outcome == "failed"


def test_rec_01_fails_when_work_is_sent(tmp_path) -> None:
    sent = {
        "method": "Network.requestWillBeSent",
        "params": {
            "request": {
                "method": "POST",
                "url": "http://127.0.0.1:5173/api/generate?x=1",
            }
        },
    }
    journey = _journey(Page(events=[sent]), tmp_path)
    asyncio.run(gj.rec_01(journey))
    record = journey.record.finish()
    assert record.work_requests == ["http://127.0.0.1:5173/api/generate"]
    assert record.outcome == "failed"


@pytest.mark.parametrize("label", ["Approve", "Allow once", "Grant access", "accept"])
def test_the_runner_never_presses_an_approval(tmp_path, label) -> None:
    page = Page(button=label)
    journey = _journey(page, tmp_path)
    with pytest.raises(gj.JourneyRefused, match="approving is the operator's act"):
        asyncio.run(journey.click("button.decision"))
    assert page.clicked == []


@pytest.mark.parametrize("label", ["Stop", "Deny"])
def test_the_runner_may_press_stop_or_deny(tmp_path, label) -> None:
    page = Page(button=label)
    asyncio.run(_journey(page, tmp_path).click("button.decision"))
    assert len(page.clicked) == 1


def test_the_journey_chrome_is_gagos_own_and_listens_locally(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(gj.eye, "chrome", lambda: "chrome.exe")
    argv = gj.launch_argv(gj.FACE_URL, tmp_path / "journey-profile")
    assert f"--user-data-dir={tmp_path / 'journey-profile'}" in argv
    assert "--remote-debugging-address=127.0.0.1" in argv
    assert "--remote-debugging-port=0" in argv
    assert argv[-1] == gj.FACE_URL
    with pytest.raises(gj.eye.EyeUnavailable):
        gj.launch_argv("--user-data-dir=C:/elsewhere", tmp_path)


def test_the_devtools_port_is_read_from_the_profile(tmp_path) -> None:
    (tmp_path / "DevToolsActivePort").write_text(
        "51234\n/devtools/browser/x\n", encoding="utf-8"
    )
    assert gj.devtools_port(tmp_path, timeout_s=1) == 51234


def test_the_face_is_reached_where_vite_serves_it() -> None:
    """2026-11-15: Vite answers on localhost (IPv6 on Windows); 127.0.0.1 is
    refused, so the eye's screenshots and the journeys never saw the face."""
    assert gj.FACE_URL == "http://localhost:5173/"
    assert gj.eye.DEFAULT_URL == "http://localhost:5173/"


def test_rec_01_counts_a_remount_as_the_one_recovery(tmp_path) -> None:
    """2026-11-15, the first run on the real face: no in-place restore came,
    and after its 4 s grace the face mounted a fresh canvas three.js ran."""
    journey = _journey(Page(restores=0, remounts=True), tmp_path)
    asyncio.run(gj.rec_01(journey))
    record = journey.record.finish()
    (once,) = [s for s in record.steps if s.name == "recovered once"]
    assert once.ok and once.detail == "0 in-place restore(s), 1 remount(s)"
    assert record.outcome == "passed"


def test_rec_01_fails_when_the_view_never_recovers(tmp_path) -> None:
    journey = _journey(Page(restores=0, remounts=False), tmp_path)
    asyncio.run(gj.rec_01(journey))
    assert journey.record.finish().outcome == "failed"


def test_rec_01_fails_when_the_view_recovers_twice(tmp_path) -> None:
    journey = _journey(Page(restores=1, remounts=True), tmp_path)
    asyncio.run(gj.rec_01(journey))
    assert journey.record.finish().outcome == "failed"


def test_rec_01_follows_the_faces_retry_when_it_does_not_restore_itself(
    tmp_path,
) -> None:
    """2026-11-15, the real face: the scene is taken down at the loss and its
    fallback offers "Retry visual organism"; the journey presses Retry (never
    an approval) and expects exactly one recovery."""
    page = Page(restores=0, remounts=False, fallback=True, retry_recovers=True)
    journey = _journey(page, tmp_path)
    asyncio.run(gj.rec_01(journey))
    record = journey.record.finish()
    steps = {s.name: s for s in record.steps}
    assert steps["fallback shown, controls still working"].ok
    assert steps["recovered once"].detail == "0 in-place restore(s), 1 remount(s)"
    assert record.outcome == "passed"
    assert any("lm-renderer-fallback__retry" in c for c in page.clicked)


def test_rec_01_fails_when_retry_does_not_bring_the_view_back(tmp_path) -> None:
    page = Page(restores=0, remounts=False, fallback=True, retry_recovers=False)
    journey = _journey(page, tmp_path)
    asyncio.run(gj.rec_01(journey))
    assert journey.record.finish().outcome == "failed"
