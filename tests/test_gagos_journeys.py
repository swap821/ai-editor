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
        body: bool = True,
        counts_remount: bool = True,
    ) -> None:
        self.body = body
        #: Since GAGOS's #700 (2026-11-16) the face counts a remount's recovery
        #: when the fresh canvas first renders; before, it never did.
        self.counts_remount = counts_remount
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
        if "__gagosBodyDraws" in expression:
            return {"draws": 2400 if self.body else 0, "frames": 60}
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
        if "c !== lost" in expression and "||" in expression:
            return restored or self.remounts  # the wait: either recovery
        if "c !== lost" in expression:
            return self.remounts
        if ".some(m => m.name === 'context-recovery')" in expression:
            return restored
        if "__gagosJourney?.metrics" in expression:
            counted = self.remounts and self.counts_remount
            return self.metrics + (
                [{"name": "context-recovery", "value": 900}] if counted else []
            )
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
    assert not once.ok
    assert (
        once.detail == "the runner saw 0 remount(s); the face counted 2 recovery(ies)"
    )
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
    and the face mounted a fresh canvas three.js ran. Since #700 the face
    counts that recovery itself; the runner's sight and the face's count are
    one recovery, not two."""
    journey = _journey(Page(restores=0, remounts=True), tmp_path)
    asyncio.run(gj.rec_01(journey))
    record = journey.record.finish()
    steps = {s.name: s for s in record.steps}
    once = steps["recovered once"]
    assert once.ok
    assert (
        once.detail == "the runner saw 1 remount(s); the face counted 1 recovery(ies)"
    )
    assert steps["the face counted its recovery"].ok
    assert record.outcome == "passed"


def test_rec_01_fails_when_the_face_does_not_count_its_remount(tmp_path) -> None:
    """Before #700: the view came back, and the face's own metric said
    nothing ("0 in-place restore(s), 1 remount(s)" on 2026-11-15)."""
    journey = _journey(Page(restores=0, remounts=True, counts_remount=False), tmp_path)
    asyncio.run(gj.rec_01(journey))
    record = journey.record.finish()
    steps = {s.name: s for s in record.steps}
    assert steps["recovered once"].ok
    counted = steps["the face counted its recovery"]
    assert not counted.ok
    assert counted.detail == "0 context-recovery sample(s) from the face's own metric"
    assert record.outcome == "failed"


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
    assert steps["recovered once"].detail == (
        "the runner saw 1 remount(s); the face counted 1 recovery(ies)"
    )
    assert record.outcome == "passed"
    assert any("lm-renderer-fallback__retry" in c for c in page.clicked)


def test_rec_01_fails_when_the_canvas_draws_no_body(tmp_path) -> None:
    """2026-11-15, the real face: its canvas was up, no fallback shown, and
    its scene held nothing; REC-01 had passed 9/9 over it."""
    journey = _journey(Page(body=False), tmp_path)
    asyncio.run(gj.rec_01(journey))
    record = journey.record.finish()
    steps = {s.name: s for s in record.steps}
    drawn = steps["the 3D body is drawn"]
    assert not drawn.ok
    assert drawn.detail == "0 WebGL draw calls over 60 frames on the scene canvas"
    assert record.outcome == "failed"


def test_rec_01_fails_when_retry_does_not_bring_the_view_back(tmp_path) -> None:
    page = Page(restores=0, remounts=False, fallback=True, retry_recovers=False)
    journey = _journey(page, tmp_path)
    asyncio.run(gj.rec_01(journey))
    assert journey.record.finish().outcome == "failed"


class PerfPage:
    """A stand-in face for PERF-01: its frames, its keys and its scene."""

    def __init__(
        self, *, frames, inputs, scene_up=True, draw_calls="40", body=True
    ) -> None:
        self.body = body
        self.frames, self.inputs = frames, inputs
        self.scene_up, self.draw_calls = scene_up, draw_calls
        self.value = "held draft"
        self.task_s = 10.0
        self.events: list[dict] = []
        self.keys: list[dict] = []

    async def send(self, method: str, **params):
        if method == "Performance.getMetrics":
            self.task_s += 0.4
            return {"metrics": [{"name": "TaskDuration", "value": self.task_s}]}
        if method == "Input.dispatchKeyEvent":
            self.keys.append(params)
            if params["type"] == "keyDown":
                self.value += params["text"]
            elif params["type"] == "rawKeyDown" and params["key"] == "Backspace":
                self.value = self.value[:-1]
        return {}

    async def evaluate(self, expression: str):
        if "__gagosBodyDraws" in expression:
            return {"draws": 2400 if self.body else 0, "frames": 60}
        if "data-controls-ready" in expression and "Boolean(" in expression:
            return True
        if "WEBGL_debug_renderer_info" in expression:
            return {
                "userAgent": "Mozilla/5.0 Chrome/157",
                "gpu": "ANGLE (AMD Radeon)",
                "cores": 12,
                "viewport": "1264x625",
                "dpr": 1,
                "build": "built bundle",
                "detail": "auto",
                "gpuTimer": False,
            }
        if "lm-renderer-fallback-notice" in expression:
            return self.scene_up
        if "window.__gagosPerf = " in expression:
            return True
        if "p.stop = true" in expression:
            return {
                "frames": self.frames,
                "inputs": self.inputs,
                "slowEvents": 0,
                "longFrames": 1,
                "slowest": [
                    {
                        "ms": 417.6,
                        "blocking": 367.6,
                        "scripts": [
                            {
                                "ms": 301.2,
                                "invoker": "DOMWindow.onmessage",
                                "source": "/node_modules/.vite/deps/react-dom.js",
                                "fn": "performWorkUntilDeadline",
                            }
                        ],
                    }
                ],
                "foreground": True,
            }
        if "gagosSceneDrawCalls" in expression:
            return {
                "drawCalls": self.draw_calls,
                "geometries": "12",
                "textures": "3",
                "objects": "90",
            }
        if "?.value ?? ''" in expression:
            return self.value
        if "__gagosJourney?.metrics" in expression:
            return [{"name": "raf-interval-p95", "value": 16.8}]
        if "__gagosJourney?.errors" in expression:
            return []
        return None


def _perf(page: PerfPage, tmp_path: Path) -> gj.JourneyRecord:
    journey = gj.Journey(page, _journey(page, tmp_path).record)
    asyncio.run(gj.perf_01(journey))
    return journey.record.finish()


def test_perf_01_passes_within_the_frozen_budgets_and_says_what_points_need(
    tmp_path,
) -> None:
    page = PerfPage(frames=[16.7] * 1200, inputs=[12.0] * len(gj.PERF_KEYS))
    record = _perf(page, tmp_path)
    assert record.outcome == "passed", [(s.name, s.ok, s.detail) for s in record.steps]
    assert page.value == "held draft"  # the composer as it was
    assert record.measured["frame_p95_ms"] == 16.7
    assert record.measured["main thread a frame (mean)"] == "0.3 ms"
    assert record.measured["slowest frames, with their scripts"] == [
        "417.6 ms (blocking 367.6 ms): 301.2 ms in "
        "/node_modules/.vite/deps/react-dom.js performWorkUntilDeadline "
        "(DOMWindow.onmessage)"
    ]
    text = gj.write_record(record, tmp_path).read_text(encoding="utf-8")
    assert "## Measured" in text and "FROZE on 2026-11-16" in text
    assert "the named desktop, headed, on the build that ships" in text
    assert "- slowest frames, with their scripts:\n  - 417.6 ms (blocking" in text
    assert "unavailable: the browser offers no EXT_disjoint_timer_query_webgl2" in text


def test_perf_01_fails_when_typing_stalls_the_face(tmp_path) -> None:
    """2026-11-15 on the dev server: keydown to the next frame p95 241 ms."""
    inputs = [16.0] * 20 + [240.9, 300.0, 595.7]
    record = _perf(PerfPage(frames=[16.7] * 1200, inputs=inputs), tmp_path)
    (keys,) = [
        s for s in record.steps if s.name.startswith("keydown to the next frame")
    ]
    assert not keys.ok and "p95 300.0 ms" in keys.detail
    assert record.outcome == "failed"


def test_perf_01_fails_when_the_scene_is_not_drawn(tmp_path) -> None:
    """2026-11-15: a production build measured fast because its scene had
    crashed at load; frames without the being are not PERF-01's."""
    page = PerfPage(frames=[16.7] * 1200, inputs=[12.0] * 23, scene_up=False)
    record = _perf(page, tmp_path)
    steps = {s.name: s for s in record.steps}
    assert not steps["the 3D scene is up"].ok
    assert record.outcome == "failed"


def test_perf_01_fails_when_the_canvas_holds_no_body(tmp_path) -> None:
    """2026-11-15: the canvas was up with no fallback, the scene empty; the
    frames and keys first measured were of a page without its body."""
    page = PerfPage(frames=[16.7] * 1200, inputs=[12.0] * 23, body=False)
    record = _perf(page, tmp_path)
    steps = {s.name: s for s in record.steps}
    assert steps["the 3D scene is up"].ok and not steps["the 3D body is drawn"].ok
    assert not steps["the body still drawn after the window"].ok
    assert record.outcome == "failed"


def test_body_draws_are_counted_on_the_scene_canvas_and_put_back() -> None:
    expression = gj._BODY_DRAWS
    assert (
        json.dumps(gj.CANVAS) in expression and "this.canvas === canvas" in expression
    )
    assert "proto[name] = original" in expression  # the context's methods restored
    # No canvas yet still takes its second, so a wait for the body waits.
    assert expression.index("setTimeout(done, 1000)") < expression.index("names = [")
    # 2026-11-15: a canvas that first mounted after the loss was attempted
    # (there was none to lose) was counted as the one remount.
    assert "lost && c && c !== lost" in gj._REMOUNTED


def test_perf_01_fails_when_the_face_counts_no_draw_calls(tmp_path) -> None:
    page = PerfPage(frames=[16.7] * 1200, inputs=[12.0] * 23, draw_calls="unavailable")
    record = _perf(page, tmp_path)
    (accounting,) = [s for s in record.steps if s.name == "composer frame accounting"]
    assert not accounting.ok and record.outcome == "failed"


@pytest.mark.parametrize("key", ["Enter", "\n", "1", "Tab"])
def test_the_runner_never_sends_the_composer(tmp_path, key) -> None:
    page = PerfPage(frames=[], inputs=[])
    journey = gj.Journey(page, _journey(page, tmp_path).record)
    with pytest.raises(gj.JourneyRefused, match="letters and Backspace"):
        asyncio.run(journey.press(key))
    assert page.keys == []


def test_percentiles_are_nearest_rank_as_the_face_computes_them() -> None:
    values = [float(v) for v in range(1, 101)]
    assert gj.percentile(values, 0.5) == 50.0
    assert gj.percentile(values, 0.95) == 95.0
    assert gj.percentile([], 0.95) is None


def test_the_record_pins_the_tree_that_serves_the_face(monkeypatch) -> None:
    """2026-11-15: the runner pinned its own checkout's commit, while the face
    was served from another tree at another commit."""
    import sys
    import types

    vite = r"C:\Users\op\ai-editor\frontend\node_modules\.bin\..\vite\bin\vite.js"
    fake = types.SimpleNamespace(
        CONN_LISTEN="LISTEN",
        Error=Exception,
        net_connections=lambda kind: [
            types.SimpleNamespace(
                status="LISTEN", laddr=types.SimpleNamespace(port=5173), pid=7
            )
        ],
        Process=lambda pid: types.SimpleNamespace(
            cmdline=lambda: ["node", vite, "--port", "5173"],
            cwd=lambda: r"C:\Users\op\ai-editor\frontend",
        ),
    )
    monkeypatch.setitem(sys.modules, "psutil", fake)
    assert gj.served_tree("http://localhost:5173/") == Path(r"C:\Users\op\ai-editor")
    assert gj.served_tree("http://localhost:4173/") is None
    assert gj.served_commit("http://localhost:4173/") == (
        "unknown",
        "the tree serving the face could not be found",
    )


def test_perf_01_judges_by_the_budgets_the_blueprint_records_frozen() -> None:
    """The operator froze two budgets on 2026-11-16 (blueprint section 10's dated
    note): the journey and the blueprint must say the same numbers."""
    blueprint = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "frontend"
        / "LIVING_BEING_BLUEPRINT_2026-09-24.md"
    ).read_text(encoding="utf-8")
    note = blueprint[blueprint.index("**Frozen by the operator, 2026-11-16.**") :][:900]
    assert "p95 frame interval ≤20 ms" in note
    assert "under 100 ms" in note
    assert gj.PERF_TARGETS == {"frame_p95_ms": 20.0, "input_to_paint_ms": 100.0}


def test_a_run_on_a_port_nothing_serves_writes_no_record(monkeypatch, tmp_path) -> None:
    """2026-11-16: the operator's two runs on :3000, before anything served it,
    wrote "controls ready: FAIL" records about a face that was never there."""
    import socket

    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    url = f"http://127.0.0.1:{port}/"
    assert gj.face_unreached(url).startswith(f"nothing answers at {url}")

    def never(*_args, **_kwargs):
        pytest.fail("the runner went on past an empty port")

    monkeypatch.setattr(gj.eye, "profile", lambda name: tmp_path)
    monkeypatch.setattr(gj, "devtools_port", lambda profile, **kw: 9)
    monkeypatch.setattr(gj, "write_record", never)
    monkeypatch.setattr(gj, "served_commit", never)
    monkeypatch.setattr(gj.subprocess, "Popen", never)
    for argv in (
        ["open", "--url", url],
        ["run", "perf-01", "--url", url],
        ["watch", "ask-01", "--url", url],
    ):
        assert gj.main(argv) == 2


def test_any_answer_counts_as_a_face_being_there() -> None:
    import http.server
    import threading

    class NotFound(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - the stdlib's name
            self.send_response(404)
            self.end_headers()

        def log_message(self, *_args) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), NotFound)
    threading.Thread(target=server.handle_request, daemon=True).start()
    try:
        assert gj.face_unreached(f"http://127.0.0.1:{server.server_port}/") is None
    finally:
        server.server_close()
