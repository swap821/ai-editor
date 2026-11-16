#!/usr/bin/env python3
"""GAGOS's browser journeys over its own face (2026-11-15).

The operator chose "option 1" for the face's 10/10: most of the acceptance
ledger's points (docs/frontend/LIVING_BEING_ACCEPTANCE_LEDGER_2026-09-24.md)
need a real browser run on the supported route, not more code. This runner
drives GAGOS's own Chrome (its eye's journey profile, never the operator's)
through Chrome's DevTools protocol and writes each run as an evidence record
pinned to the commit, the browser and the viewport.

  open           GAGOS's journey window on the face, for the operator to sign in
  run <id>       one journey; its record goes to docs/frontend/evidence/journeys/
  list           the journeys and the ledger criterion each one serves

Its rules, held in code:

* DevTools listens on 127.0.0.1 only, in GAGOS's own profile;
* it never types a credential: the operator signs in himself, once, in the
  journey window;
* it never approves: :meth:`Journey.click` refuses an Allow or Approve control,
  and a step that needs an approval waits for the operator's own click;
* every record says what the run does NOT prove (its boundary), as the
  ledger's own evidence records do. A partial run earns no points; the ledger's
  rules decide what a criterion needs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools import gagos_eye as eye  # noqa: E402

FACE_URL = "http://localhost:5173/"
#: The face's API base as frontend/src/config.js derives it: on the dev server
#: the backend on localhost:8000 (the host its session cookie belongs to; not
#: AIOS_PROBE_BASE's 127.0.0.1, whose cookies are another host's), and the built
#: bundle its own origin. The face's dev origin answers the backend's routes
#: with the page itself. VITE_API_BASE overrides are not followed.
FACE_DEV_API_BASE = "http://localhost:8000"
_FACE_API_BASE = (
    "(document.querySelector('script[src*=\"/@vite/client\"]') ? "
    + json.dumps(FACE_DEV_API_BASE)
    + " : location.origin)"
)
EVIDENCE_DIR = REPO / "docs" / "frontend" / "evidence" / "journeys"
#: The composer and the scene, as the face marks them (SuperbrainApp.jsx).
COMPOSER = '[aria-label="Talk to GAGOS"]'
CANVAS = ".scene-layer canvas"
CONTROLS_READY = '[data-controls-ready="true"]'
#: The face's own notice when its visual organism is down, and its Retry.
FALLBACK = ".lm-renderer-fallback-notice"
RETRY = ".lm-renderer-fallback__retry"
#: Controls the runner may never press: approving is the operator's own act.
FORBIDDEN_CONTROL = re.compile(r"\b(approve|allow|grant|accept)\b", re.IGNORECASE)
#: Requests that would start backend work: a journey that only holds a draft
#: must send none.
WORK_REQUEST = re.compile(r"/api/(v1/)?(generate|chat)(/|\?|$)")
#: Collected inside the page: the face's own metric events, and the console.
_PAGE_PROBE = """
(() => {
  if (window.__gagosJourney) return;
  window.__gagosJourney = { metrics: [], errors: [] };
  window.addEventListener('gagos:frontend-metric', (e) => {
    window.__gagosJourney.metrics.push({ name: e.detail.name, value: e.detail.value });
  });
  window.addEventListener('error', (e) => {
    window.__gagosJourney.errors.push(String(e.message || e.type));
  });
})();
"""


class JourneyRefused(RuntimeError):
    """A step the runner may not take, or cannot."""


# ------------------------------------------------------------------ the browser


def launch_argv(url: str, profile: Path, *, headless: bool = False) -> list[str]:
    """GAGOS's journey Chrome: its own profile, DevTools on 127.0.0.1 on a
    port Chrome chooses (written to DevToolsActivePort in the profile)."""
    argv = [
        eye.chrome(),
        f"--user-data-dir={profile}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=0",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,720",
    ]
    if headless:
        argv.append("--headless=new")
    return [*argv, eye.page_url(url)]


def devtools_port(profile: Path, *, timeout_s: float = 30.0) -> int:
    """The port Chrome wrote for its DevTools, once it is listening."""
    marker = profile / "DevToolsActivePort"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if marker.is_file():
            first = marker.read_text(encoding="utf-8").splitlines()[:1]
            if first and first[0].strip().isdigit():
                return int(first[0])
        time.sleep(0.25)
    raise JourneyRefused("Chrome's DevTools did not start")


def page_socket(port: int, url_prefix: str) -> str:
    """The DevTools socket of the open face tab."""
    with urllib.request.urlopen(  # noqa: S310 - 127.0.0.1, a fixed path
        f"http://127.0.0.1:{port}/json/list", timeout=10
    ) as response:
        targets = json.loads(response.read().decode("utf-8"))
    for target in targets:
        if target.get("type") == "page" and str(target.get("url", "")).startswith(
            url_prefix
        ):
            return target["webSocketDebuggerUrl"]
    raise JourneyRefused(f"no tab is open on {url_prefix}")


class Cdp:
    """A small DevTools client: commands answered by id, events kept."""

    def __init__(self, socket: Any) -> None:
        self.socket = socket
        self.events: list[dict] = []
        self._next = 0

    async def send(self, method: str, **params: Any) -> dict:
        self._next += 1
        sent = self._next
        await self.socket.send(
            json.dumps({"id": sent, "method": method, "params": params})
        )
        while True:
            message = json.loads(await self.socket.recv())
            if message.get("id") == sent:
                if "error" in message:
                    raise JourneyRefused(f"{method}: {message['error'].get('message')}")
                return message.get("result", {})
            if "method" in message:
                self.events.append(message)

    async def evaluate(self, expression: str) -> Any:
        result = await self.send(
            "Runtime.evaluate",
            expression=expression,
            returnByValue=True,
            awaitPromise=True,
        )
        if result.get("exceptionDetails"):
            text = result["exceptionDetails"].get("text", "an exception")
            raise JourneyRefused(f"the page threw: {text}")
        return result.get("result", {}).get("value")


# ------------------------------------------------------------------ the record


@dataclass
class Step:
    name: str
    ok: bool
    detail: str
    at: float


@dataclass
class JourneyRecord:
    """What one run did and saw, pinned to its commit, browser and viewport."""

    journey: str
    criterion: str
    commit: str
    browser: str
    viewport: str
    url: str
    started_at: str
    signed_in: bool = False
    #: The checkout that serves the face, and whether its frontend is clean.
    tree: str = ""
    steps: list[Step] = field(default_factory=list)
    work_requests: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)
    #: What a measuring journey measured, and on what: kept beside its steps.
    measured: dict[str, Any] = field(default_factory=dict)
    outcome: str = "not run"
    boundary: str = ""

    def finish(self) -> JourneyRecord:
        """Passed only when it took steps and every one passed."""
        self.outcome = (
            "passed" if self.steps and all(s.ok for s in self.steps) else "failed"
        )
        return self

    def step(self, name: str, ok: bool, detail: str = "") -> bool:
        self.steps.append(Step(name, ok, detail, time.monotonic()))
        return ok

    def markdown(self) -> str:
        lines = [
            f"# Journey {self.journey} ({self.criterion})",
            "",
            f"Run {self.started_at} on commit `{self.commit[:12]}` "
            f"({self.tree or 'tree not recorded'}), {self.browser}, "
            f"viewport {self.viewport}, at `{self.url}`. Signed in: "
            f"{'yes' if self.signed_in else 'no'}. Outcome: **{self.outcome}**.",
            "",
            "| Step | Result | Detail |",
            "| --- | --- | --- |",
            *(
                f"| {s.name} | {'pass' if s.ok else 'FAIL'} | {s.detail} |"
                for s in self.steps
            ),
            "",
            f"Requests that start backend work: {len(self.work_requests)}"
            + (f" ({', '.join(self.work_requests)})" if self.work_requests else ""),
            f"Page errors: {len(self.page_errors)}"
            + (f" ({'; '.join(self.page_errors[:5])})" if self.page_errors else ""),
            "",
            *(
                [
                    "## Measured",
                    "",
                    *(
                        line
                        for k, v in self.measured.items()
                        for line in (
                            [f"- {k}:", *(f"  - {item}" for item in v)]
                            if isinstance(v, list) and v
                            else [f"- {k}: {'none' if v == [] else v}"]
                        )
                    ),
                    "",
                ]
                if self.measured
                else []
            ),
            "## Evidence boundary",
            "",
            self.boundary,
            "",
        ]
        return "\n".join(lines)


def write_record(record: JourneyRecord, dest: Path = EVIDENCE_DIR) -> Path:
    """The record as JSON and Markdown, side by side; the Markdown path."""
    dest.mkdir(parents=True, exist_ok=True)
    stem = f"{record.started_at[:10]}-{record.journey}-{record.commit[:12]}"
    (dest / f"{stem}.json").write_text(
        json.dumps(asdict(record), indent=2) + "\n", encoding="utf-8"
    )
    md = dest / f"{stem}.md"
    md.write_text(record.markdown(), encoding="utf-8")
    return md


# ------------------------------------------------------------------ the journey


class Journey:
    """One run's actions on the face, each kept in its record."""

    def __init__(self, cdp: Cdp, record: JourneyRecord) -> None:
        self.cdp, self.record = cdp, record

    async def start(self) -> None:
        await self.cdp.send("Page.enable")
        await self.cdp.send("Network.enable")
        await self.cdp.send("Page.addScriptToEvaluateOnNewDocument", source=_PAGE_PROBE)
        await self.cdp.evaluate(_PAGE_PROBE)

    async def wait_for(self, expression: str, timeout_s: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if await self.cdp.evaluate(f"Boolean({expression})"):
                return True
            await asyncio.sleep(0.25)
        return False

    async def signed_in(self) -> bool:
        """Whether the page's session is the operator's: only the yes or no is
        kept, never his id or the session's token."""
        status = await self.cdp.evaluate(
            f"fetch({_FACE_API_BASE} + '/api/v1/auth/session', {{credentials: 'include'}})"
            ".then(r => r.ok ? r.json() : {}).then(s => Boolean(s.authenticated))"
            ".catch(() => false)"
        )
        self.record.signed_in = bool(status)
        return self.record.signed_in

    async def click(self, selector: str) -> None:
        text = await self.cdp.evaluate(
            f"(document.querySelector({json.dumps(selector)})?.innerText || "
            f"document.querySelector({json.dumps(selector)})?.getAttribute('aria-label') "
            "|| '')"
        )
        if FORBIDDEN_CONTROL.search(str(text or "")):
            raise JourneyRefused(
                f"the runner never presses {text!r}: approving is the operator's act"
            )
        await self.cdp.evaluate(
            f"document.querySelector({json.dumps(selector)}).click()"
        )

    async def type_into(self, selector: str, text: str) -> None:
        await self.cdp.evaluate(
            f"document.querySelector({json.dumps(selector)}).focus()"
        )
        await self.cdp.send("Input.insertText", text=text)

    async def press(self, key: str) -> None:
        """One key, as a keyboard sends it: a letter, or Backspace. Never Enter:
        a journey never sends the composer; sending is the operator's act."""
        if key == "Backspace":
            down = {"key": key, "code": key, "windowsVirtualKeyCode": 8}
            kind = "rawKeyDown"
        elif len(key) == 1 and key.isalpha():
            down = {
                "key": key,
                "text": key,
                "code": f"Key{key.upper()}",
                "windowsVirtualKeyCode": ord(key.upper()),
            }
            kind = "keyDown"
        else:
            raise JourneyRefused(
                f"the runner presses letters and Backspace, not {key!r}"
            )
        await self.cdp.send("Input.dispatchKeyEvent", type=kind, **down)
        up = {k: v for k, v in down.items() if k != "text"}
        await self.cdp.send("Input.dispatchKeyEvent", type="keyUp", **up)

    async def value_of(self, selector: str) -> str:
        return str(
            await self.cdp.evaluate(
                f"document.querySelector({json.dumps(selector)})?.value ?? ''"
            )
        )

    async def metrics(self) -> list[dict]:
        return list(
            await self.cdp.evaluate("window.__gagosJourney?.metrics || []") or []
        )

    async def collect(self) -> None:
        """The run's work requests and page errors, from the browser itself."""
        for event in self.cdp.events:
            if event.get("method") != "Network.requestWillBeSent":
                continue
            request = event.get("params", {}).get("request", {})
            if request.get("method") == "POST" and WORK_REQUEST.search(
                str(request.get("url", ""))
            ):
                self.record.work_requests.append(str(request["url"]).split("?")[0])
        self.record.page_errors = list(
            await self.cdp.evaluate("window.__gagosJourney?.errors || []") or []
        )
        self.record.metrics = await self.metrics()


async def rec_01(j: Journey) -> None:
    """REC-01, renderer and backend recovery (weight 3): a draft in the
    composer survives the 3D view losing its graphics context and the network
    dropping; the view recovers once (restored in place, or remounted);
    nothing is sent twice (here: nothing at all, since the draft is never
    sent)."""
    r = j.record
    r.boundary = (
        "A draft only, with no live work in flight: this proves the draft, the "
        "view's single recovery and that no work request was sent across a "
        "graphics-context loss and a network drop. It does not prove a pending "
        "decision or a receipt surviving them during real work, which REC-01's "
        "full threshold also needs; REC-01 earns no points from this run alone."
    )
    if not r.step(
        "controls ready",
        await j.wait_for(f"document.querySelector('{CONTROLS_READY}')", 60),
    ):
        return
    # 2026-11-15: REC-01 first passed on a canvas whose scene was empty; a
    # recovery of a view that draws nothing proves little.
    await body_drawn(j, "the 3D body is drawn", within=20)
    await j.signed_in()
    draft = f"journey draft {int(time.time())}"
    await j.type_into(COMPOSER, draft)
    r.step("draft typed", await j.value_of(COMPOSER) == draft)
    lost = await j.cdp.evaluate(
        "(() => { const c = document.querySelector('" + CANVAS + "');"
        " const gl = c && (c.getContext('webgl2') || c.getContext('webgl'));"
        " const ext = gl && gl.getExtension('WEBGL_lose_context');"
        " if (!ext) return false; window.__gagosJourneyLoss = ext;"
        " window.__gagosJourneyCanvas = c;"
        " ext.loseContext(); return true; })()"
    )
    r.step(
        "graphics context lost", bool(lost), "WEBGL_lose_context on the scene canvas"
    )
    await asyncio.sleep(2)
    r.step("draft kept while the view is lost", await j.value_of(COMPOSER) == draft)
    await j.cdp.evaluate(
        "window.__gagosJourneyLoss && window.__gagosJourneyLoss.restoreContext()"
    )
    # 2026-11-15, the first runs on the real face: it did not restore in place
    # (the scene is taken down at the loss) but showed its fallback with a
    # Retry; recovery is that Retry. Either way counts, once.
    if not await j.wait_for(f"{_IN_PLACE} || {_REMOUNTED}", 6):
        fallback = await j.wait_for(f"document.querySelector('{FALLBACK}')", 5)
        r.step(
            "fallback shown, controls still working",
            fallback
            and bool(
                await j.cdp.evaluate(
                    f"Boolean(document.querySelector('{CONTROLS_READY}'))"
                )
            ),
        )
        if fallback:
            await j.click(RETRY)
            await j.wait_for(f"{_IN_PLACE} || {_REMOUNTED}", 20)
    await body_drawn(j, "the 3D body is drawn again", within=20)
    # Read after the body draws again: the face counts a remount's recovery
    # when the fresh canvas first renders (2026-11-16, GAGOS's #700), and its
    # count covers an in-place restore too. The runner sees only a remount.
    counted = sum(1 for m in await j.metrics() if m.get("name") == "context-recovery")
    remounted = 1 if await j.cdp.evaluate(_REMOUNTED) else 0
    r.step(
        "recovered once",
        max(counted, remounted) == 1 and counted <= 1,
        f"the runner saw {remounted} remount(s); the face counted {counted} recovery(ies)",
    )
    r.step(
        "the face counted its recovery",
        counted == 1,
        f"{counted} context-recovery sample(s) from the face's own metric",
    )
    await j.cdp.send(
        "Network.emulateNetworkConditions",
        offline=True,
        latency=0,
        downloadThroughput=-1,
        uploadThroughput=-1,
    )
    await asyncio.sleep(5)
    r.step("draft kept while offline", await j.value_of(COMPOSER) == draft)
    await j.cdp.send(
        "Network.emulateNetworkConditions",
        offline=False,
        latency=0,
        downloadThroughput=-1,
        uploadThroughput=-1,
    )
    await j.cdp.send("Page.reload")
    # Right after a reload the old page may still answer; wait for the draft
    # itself to come back (2026-11-15: read too early, it looked lost).
    await asyncio.sleep(1)
    back = await j.wait_for(
        f"document.querySelector({json.dumps(COMPOSER)})?.value === {json.dumps(draft)}",
        30,
    )
    r.step("draft back after a reload", back)
    await j.collect()
    r.step("no work request sent", not r.work_requests, f"{len(r.work_requests)} sent")


#: The face has counted a recovery (an in-place restore; since #700 also the
#: first frame of a remounted canvas).
_IN_PLACE = (
    "(window.__gagosJourney.metrics || []).some(m => m.name === 'context-recovery')"
)
#: A fresh canvas after the one lost; a canvas that first mounts after the loss
#: was attempted (none there to lose) is not a remount.
_REMOUNTED = (
    "(() => { const c = document.querySelector('" + CANVAS + "');"
    " const lost = window.__gagosJourneyCanvas;"
    " return Boolean(lost && c && c !== lost && c.dataset.engine); })()"
)

#: PERF-01's budgets, blueprint section 10: the smooth tier's p95 frame
#: interval, and local feedback. Frozen by the operator on 2026-11-16.
PERF_TARGETS = {"frame_p95_ms": 20.0, "input_to_paint_ms": 100.0}
PERF_WARMUP_S = 5.0
PERF_WINDOW_S = 20.0
#: Typed into the composer across the window, then taken back out.
PERF_KEYS = "gagosmeasuresitsownface"
#: Named, in the page: the GPU the browser draws with, the viewport, the build
#: and the visual detail chosen. A throwaway canvas, released at once.
_PERF_ENV = """(() => {
  const c = document.createElement('canvas');
  const gl = c.getContext('webgl2') || c.getContext('webgl');
  const info = gl && gl.getExtension('WEBGL_debug_renderer_info');
  const out = {
    userAgent: navigator.userAgent,
    gpu: gl ? String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER))
      : 'unavailable',
    cores: navigator.hardwareConcurrency || null,
    viewport: innerWidth + 'x' + innerHeight,
    dpr: devicePixelRatio,
    build: document.querySelector('script[src*="/@vite/client"]')
      ? 'Vite dev server' : 'built bundle',
    detail: document.querySelector('.lm-rendering-preferences select')?.value
      || 'unavailable',
    gpuTimer: Boolean(gl && gl.getExtension('EXT_disjoint_timer_query_webgl2')),
  };
  const lose = gl && gl.getExtension('WEBGL_lose_context');
  if (lose) lose.loseContext();
  return out;
})()"""
#: Every frame interval, and keydown in the composer to the end of the next
#: frame, measured in the page; the browser's own slow-interaction and
#: long-frame counts beside them, and its five slowest frames with the scripts
#: that ran in them (where the browser can tell: Long Animation Frames).
_PERF_PROBE = """(() => {
  const p = window.__gagosPerf = { frames: [], inputs: [], slowEvents: 0,
    longFrames: 0, slowest: [], stop: false };
  const where = (url) => String(url || '').replace(location.origin, '').split('?')[0];
  let previous = null;
  const tick = (now) => {
    if (p.stop) return;
    if (previous !== null) p.frames.push(now - previous);
    previous = now;
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  window.addEventListener('keydown', (e) => {
    if (p.stop || !(e.target instanceof Element) || !e.target.matches(SELECTOR)) return;
    const t0 = e.timeStamp;
    requestAnimationFrame(() => {
      const channel = new MessageChannel();
      channel.port1.onmessage = () => p.inputs.push(performance.now() - t0);
      channel.port2.postMessage(0);
    });
  }, { capture: true, passive: true });
  try {
    new PerformanceObserver((l) => { p.slowEvents += l.getEntries().length; })
      .observe({ type: 'event', durationThreshold: 104 });
  } catch (e) { p.slowEvents = null; }
  try {
    new PerformanceObserver((l) => {
      if (p.stop) return;
      for (const f of l.getEntries()) {
        p.longFrames += 1;
        p.slowest.push({ ms: f.duration, blocking: f.blockingDuration,
          scripts: [...(f.scripts || [])].sort((a, b) => b.duration - a.duration)
            .slice(0, 3).map((s) => ({ ms: s.duration, invoker: s.invoker,
              source: where(s.sourceURL), fn: s.sourceFunctionName })) });
        p.slowest.sort((a, b) => b.ms - a.ms);
        p.slowest.length = Math.min(p.slowest.length, 5);
      }
    }).observe({ type: 'long-animation-frame' });
  } catch (e) { p.longFrames = null; }
  return true;
})()""".replace("SELECTOR", json.dumps(COMPOSER))
_PERF_READ = (
    "(() => { const p = window.__gagosPerf; p.stop = true; return {frames: p.frames,"
    " inputs: p.inputs, slowEvents: p.slowEvents, longFrames: p.longFrames,"
    " slowest: p.slowest,"
    " foreground: document.visibilityState === 'visible'}; })()"
)
#: The face's own scene probe (frontendMetrics.ts, local hosts only).
_SCENE = (
    "(() => { const d = document.documentElement.dataset; return {"
    " drawCalls: d.gagosSceneDrawCalls ?? 'unavailable',"
    " geometries: d.gagosSceneGeometries ?? 'unavailable',"
    " textures: d.gagosSceneTextures ?? 'unavailable',"
    " objects: d.gagosSceneObjects ?? 'unavailable'}; })()"
)
#: The being's canvas is there and the face shows no fallback.
_SCENE_UP = (
    f"Boolean(document.querySelector('{CANVAS}'))"
    f" && !document.querySelector('{FALLBACK}')"
)
#: WebGL draw calls on the scene canvas over one second, counted at the context
#: (its draw methods wrapped, then put back), beside the frames painted. The
#: face's own counters are not used: 2026-11-15, a canvas with no fallback
#: shown held an EMPTY scene, and its own probe sat inside what never mounted.
_BODY_DRAWS = """(async () => {
  window.__gagosBodyDraws = true;
  const canvas = document.querySelector(SELECTOR);
  if (!canvas) {
    // No canvas yet: a second still passes, so a caller's wait is a wait.
    await new Promise((done) => setTimeout(done, 1000));
    return {draws: 0, frames: 0};
  }
  const names = ['drawArrays', 'drawElements', 'drawArraysInstanced',
    'drawElementsInstanced', 'drawRangeElements'];
  const saved = [];
  let draws = 0;
  for (const kind of [window.WebGL2RenderingContext, window.WebGLRenderingContext]) {
    if (!kind) continue;
    for (const name of names) {
      const original = kind.prototype[name];
      if (typeof original !== 'function') continue;
      saved.push([kind.prototype, name, original]);
      kind.prototype[name] = function (...args) {
        if (this.canvas === canvas) draws += 1;
        return original.apply(this, args);
      };
    }
  }
  let frames = 0;
  let counting = true;
  const tick = () => { if (counting) { frames += 1; requestAnimationFrame(tick); } };
  requestAnimationFrame(tick);
  try {
    await new Promise((done) => setTimeout(done, 1000));
  } finally {
    counting = false;
    for (const [proto, name, original] of saved) proto[name] = original;
  }
  return {draws, frames};
})()""".replace("SELECTOR", json.dumps(CANVAS))


async def body_drawn(j: Journey, name: str, *, within: int = 1) -> bool:
    """A step: the being's body is drawn, at least one WebGL draw call a frame
    on the scene canvas, counted a second at a time for up to *within*
    seconds. An empty scene draws nothing."""
    draws = frames = 0
    drawn = False
    for _ in range(max(1, within)):
        seen = dict(await j.cdp.evaluate(_BODY_DRAWS) or {})
        draws, frames = int(seen.get("draws") or 0), int(seen.get("frames") or 0)
        drawn = frames > 0 and draws >= frames
        if drawn:
            break
    return j.record.step(
        name,
        drawn,
        f"{draws} WebGL draw calls over {frames} frames on the scene canvas",
    )


def percentile(values: list[float], p: float) -> float | None:
    """Nearest rank, as the face's own frame sampler computes it."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * p) - 1)]


def perf_summary(frames: list[float], inputs: list[float]) -> dict[str, Any]:
    """A window's frame intervals and input latencies, as distributions."""
    return {
        "frames": len(frames),
        "frame_p50_ms": percentile(frames, 0.5),
        "frame_p95_ms": percentile(frames, 0.95),
        "frame_p99_ms": percentile(frames, 0.99),
        "frame_max_ms": max(frames) if frames else None,
        "frame_gaps_over_50ms": sum(1 for f in frames if f > 50),
        "inputs": len(inputs),
        "input_p50_ms": percentile(inputs, 0.5),
        "input_p95_ms": percentile(inputs, 0.95),
        "input_max_ms": max(inputs) if inputs else None,
    }


def _ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f} ms"


def slow_frame(frame: dict) -> str:
    """One long animation frame and the scripts that ran longest in it, as
    the browser attributes them; the rest of its time is the browser's own
    (style, layout, paint) or unattributed."""
    scripts = [
        f"{_ms(s.get('ms'))} in {s.get('source') or 'an unknown source'}"
        + (f" {s['fn']}" if s.get("fn") else "")
        + (f" ({s['invoker']})" if s.get("invoker") else "")
        for s in frame.get("scripts") or []
    ]
    return f"{_ms(frame.get('ms'))} (blocking {_ms(frame.get('blocking'))}): " + (
        "; ".join(scripts) if scripts else "no script attributed"
    )


async def _task_seconds(j: Journey) -> float | None:
    """Chrome's main-thread task time so far, in seconds."""
    result = await j.cdp.send("Performance.getMetrics")
    for metric in result.get("metrics", []):
        if metric.get("name") == "TaskDuration":
            return float(metric["value"])
    return None


async def perf_01(j: Journey) -> None:
    """PERF-01, desktop frame and input budget (weight 4): over a window of the
    face at rest with letters typed into its composer, every frame interval,
    keydown to the next frame, the main thread's time a frame and the
    composer's draw calls, on a named desktop, against the budgets the
    operator froze. The composer is left as it was; nothing is sent."""
    r = j.record
    r.boundary = (
        "Compared with the budgets the operator FROZE on 2026-11-16 (blueprint "
        "section 10: p95 frame interval at most 20 ms on the smooth tier, local "
        "feedback under 100 ms). PERF-01 earns points only on the named desktop, "
        "headed, on the build that ships, before any visual-load change. Keydown to the next "
        "frame is measured in the page, not from the key to the screen. GPU time "
        "is unavailable unless the browser offers its timer extension, and an "
        "unavailable counter is never read as zero cost. Draw calls are the "
        "face's own count, not VRAM. A headless run, or one on the Vite dev "
        "server, is a smoke, not the named desktop profile."
    )
    if not r.step(
        "controls ready",
        await j.wait_for(f"document.querySelector('{CONTROLS_READY}')", 60),
    ):
        return
    await j.cdp.send("Page.bringToFront")
    env = dict(await j.cdp.evaluate(_PERF_ENV) or {})
    headless = "Headless" in str(env.get("userAgent", ""))
    r.measured.update(
        {
            "gpu": env.get("gpu", "unavailable"),
            "cores": env.get("cores"),
            "viewport": f"{env.get('viewport')} at DPR {env.get('dpr')}",
            "build": env.get("build"),
            "visual detail": env.get("detail"),
            "window": "headless" if headless else "headed",
            "gpu time": "available, not yet read by this journey"
            if env.get("gpuTimer")
            else "unavailable: the browser offers no EXT_disjoint_timer_query_webgl2",
            "warmup": f"{PERF_WARMUP_S:.0f} s",
            "scenario": f"the face at rest, {len(PERF_KEYS)} letters typed into "
            f"the composer across a {PERF_WINDOW_S:.0f} s window",
        }
    )
    r.step(
        "desktop named",
        r.measured["gpu"] != "unavailable",
        f"{r.measured['gpu']}; {r.measured['cores']} cores; {r.measured['viewport']};"
        f" {r.measured['build']}; {r.measured['window']}",
    )
    await asyncio.sleep(PERF_WARMUP_S)
    # 2026-11-15: a production build measured fast because its scene had
    # crashed at load; the frames of a page without its being are not PERF-01's.
    r.step(
        "the 3D scene is up",
        bool(await j.cdp.evaluate(_SCENE_UP)),
        "a scene canvas, and no renderer fallback shown",
    )
    # 2026-11-15: the canvas was up with no fallback shown, and the scene held
    # nothing; the frames and keys measured then were of a page without a body.
    await body_drawn(j, "the 3D body is drawn")
    original = await j.value_of(COMPOSER)
    await j.cdp.send("Performance.enable")
    before = await _task_seconds(j)
    await j.cdp.evaluate(_PERF_PROBE)
    await j.cdp.evaluate(f"document.querySelector({json.dumps(COMPOSER)}).focus()")
    gap = PERF_WINDOW_S / (len(PERF_KEYS) + 1)
    for key in PERF_KEYS:
        await asyncio.sleep(gap)
        await j.press(key)
    await asyncio.sleep(gap)
    sampled = dict(await j.cdp.evaluate(_PERF_READ) or {})
    after = await _task_seconds(j)
    r.step(
        "the scene stayed up through the window", bool(await j.cdp.evaluate(_SCENE_UP))
    )
    await body_drawn(j, "the body still drawn after the window")
    summary = perf_summary(
        [float(f) for f in sampled.get("frames") or []],
        [float(i) for i in sampled.get("inputs") or []],
    )
    r.measured.update(summary)
    r.measured["slow interactions (over 104 ms)"] = sampled.get("slowEvents")
    r.measured["long animation frames"] = sampled.get("longFrames")
    r.measured["slowest frames, with their scripts"] = [
        slow_frame(f) for f in sampled.get("slowest") or []
    ]
    own = [m["value"] for m in await j.metrics() if m.get("name") == "raf-interval-p95"]
    r.measured["the face's own p95 (per 120 frames), worst"] = (
        _ms(max(own)) if own else "none recorded"
    )
    foreground = bool(sampled.get("foreground"))
    r.step(
        "frames sampled",
        summary["frames"] >= 120 and foreground,
        f"{summary['frames']} frames over {PERF_WINDOW_S:.0f} s"
        + ("" if foreground else ", the page NOT in the foreground"),
    )
    target = PERF_TARGETS["frame_p95_ms"]
    p95 = summary["frame_p95_ms"]
    r.step(
        f"frame p95 within the frozen {target:.0f} ms",
        p95 is not None and p95 <= target,
        f"p50 {_ms(summary['frame_p50_ms'])}, p95 {_ms(p95)}, "
        f"p99 {_ms(summary['frame_p99_ms'])}, max {_ms(summary['frame_max_ms'])}; "
        f"{summary['frame_gaps_over_50ms']} gaps over 50 ms",
    )
    target = PERF_TARGETS["input_to_paint_ms"]
    ip95 = summary["input_p95_ms"]
    r.step(
        f"keydown to the next frame within the frozen {target:.0f} ms",
        ip95 is not None and ip95 <= target and summary["inputs"] == len(PERF_KEYS),
        f"p50 {_ms(summary['input_p50_ms'])}, p95 {_ms(ip95)}, "
        f"max {_ms(summary['input_max_ms'])} over {summary['inputs']} of "
        f"{len(PERF_KEYS)} keys",
    )
    per_frame = (
        (after - before) * 1000 / summary["frames"]
        if before is not None and after is not None and summary["frames"]
        else None
    )
    r.measured["main thread a frame (mean)"] = _ms(per_frame)
    r.step(
        "main-thread time a frame",
        per_frame is not None,
        f"{_ms(per_frame)} mean, Chrome's task time over the window",
    )
    scene = dict(await j.cdp.evaluate(_SCENE) or {})
    r.measured["scene"] = scene
    r.step(
        "composer frame accounting",
        scene.get("drawCalls") not in (None, "unavailable"),
        f"{scene.get('drawCalls')} draw calls a frame, {scene.get('geometries')} "
        f"geometries, {scene.get('textures')} textures, {scene.get('objects')} "
        "scene objects (the face's own probe)",
    )
    for _ in PERF_KEYS:
        await j.press("Backspace")
    r.step("composer as it was", await j.value_of(COMPOSER) == original)
    await j.collect()
    r.step("no work request sent", not r.work_requests, f"{len(r.work_requests)} sent")


JOURNEYS: dict[str, tuple[str, Callable[[Journey], Awaitable[None]]]] = {
    "rec-01": ("REC-01 renderer and backend recovery", rec_01),
    "perf-01": ("PERF-01 desktop frame and input budget", perf_01),
}


async def run(
    journey_id: str,
    *,
    url: str,
    port: int,
    commit: str,
    browser: str,
    tree: str = "",
) -> JourneyRecord:
    import websockets

    criterion, body = JOURNEYS[journey_id]
    record = JourneyRecord(
        journey=journey_id,
        criterion=criterion,
        commit=commit,
        browser=browser,
        tree=tree,
        viewport="1280x720",
        url=url,
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    async with websockets.connect(page_socket(port, url), max_size=None) as socket:
        journey = Journey(Cdp(socket), record)
        await journey.start()
        try:
            await body(journey)
        except JourneyRefused as exc:
            record.step("refused", False, str(exc))
    return record.finish()


# ------------------------------------------------------------------ phase 2
# The operator sends, the runner watches (2026-11-16, his yes; the design is
# docs/frontend/JOURNEYS_PHASE2_DESIGN_2026-11-16.md). The runner never sends,
# never approves or denies; it records types, sizes, ids and times only.

#: A pending decision and a receipt, as the face marks them (GagosChrome.jsx,
#: ReceiptCard.tsx), and the app root carrying the being's named state.
APPROVAL_PENDING = '.gagos-chrome[data-approval-pending="true"]'
RECEIPT = "section.gagos-receipt"
APP = ".lm-app"
#: The longest a watch waits for the operator's send and its turn's end.
WATCH_LIMIT_S = 15 * 60
#: The turn's own stream ends with one of these frames (aiosAdapter.ts).
TERMINAL_FRAMES = ("done", "error")
#: Receipts that may follow each terminal frame (receipts.ts's kinds).
RECEIPTS_AFTER = {
    "done": {"verified-success", "finished-unverified"},
    "error": {"failure", "failure-rollback", "refusal"},
}
#: In the page: each POST to /api/generate teed, its SSE frames kept by event
#: type, size and turn_id only -- never their text.
_TURN_PROBE = r"""(() => {
  if (window.__gagosTurns) return true;
  const turns = window.__gagosTurns = [];
  const original = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const response = await original(input, init);
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      if (!/\/api\/generate(\?|$)/.test(url) || !response.body) return response;
      const turn = { at: performance.now(), status: response.status, frames: [] };
      turns.push(turn);
      const reader = response.clone().body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let event = 'message';
      (async () => {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let i;
          while ((i = buffer.indexOf('\n')) >= 0) {
            const line = buffer.slice(0, i).replace(/\r$/, '');
            buffer = buffer.slice(i + 1);
            if (line.startsWith('event:')) event = line.slice(6).trim();
            else if (line.startsWith('data:')) {
              const raw = line.slice(5).trim();
              let turnId = null;
              try { const d = JSON.parse(raw); if (typeof d.turn_id === 'string') turnId = d.turn_id; } catch (e) {}
              turn.frames.push({ at: performance.now(), event, bytes: raw.length, turnId });
            } else if (line === '') event = 'message';
          }
        }
      })().catch(() => { turn.readError = true; });
    } catch (e) {}
    return response;
  };
  return true;
})()"""
#: The face's named state now: whether it works, the being's phase and task
#: state, a pending decision, the receipts shown by kind, and how long the
#: composer's draft is (its length only).
_FACE_STATE = (
    (
        "(() => { const app = document.querySelector(APP);"
        " const kinds = [...document.querySelectorAll(RECEIPT)].map(s =>"
        " ([...s.classList].find(c => c.startsWith('gagos-receipt--')) || '').slice(15) || 'unknown');"
        " return { working: app ? app.dataset.working ?? null : null,"
        " phase: app ? app.dataset.beingPhase ?? null : null,"
        " taskState: app ? app.dataset.beingTaskState ?? null : null,"
        " approval: Boolean(document.querySelector(APPROVAL)), receipts: kinds,"
        " draft: (document.querySelector(COMPOSER) || {}).value?.length ?? 0 }; })()"
    )
    .replace("APPROVAL", json.dumps(APPROVAL_PENDING))
    .replace("RECEIPT", json.dumps(RECEIPT))
    .replace("APP", json.dumps(APP))
    .replace("COMPOSER", json.dumps(COMPOSER))
)


def say(text: str) -> None:
    """A line for the operator, in his terminal."""
    print(f"[journey] {text}", flush=True)


def mirror_events(events: list[dict]) -> list[dict]:
    """The mirror stream's canonical events among CDP's events, by id, type
    and turn_id only (Network.eventSourceMessageReceived)."""
    out = []
    for event in events:
        if event.get("method") != "Network.eventSourceMessageReceived":
            continue
        params = event.get("params", {})
        try:
            data = json.loads(params.get("data") or "{}")
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        turn = payload.get("turn_id") or data.get("turn_id") or data.get("turnId")
        out.append(
            {
                "id": str(params.get("eventId") or ""),
                "type": str(data.get("eventType") or params.get("eventName") or ""),
                "turnId": turn if isinstance(turn, str) else None,
            }
        )
    return out


async def watch_turn(j: Journey, limit_s: float = WATCH_LIMIT_S) -> dict:
    """Wait for the operator's send and its turn's end, sampling the face's
    named state each second (kept when it changes). Returns the turns the
    page saw, the face's states, and whether a terminal frame came in time."""
    deadline = time.monotonic() + limit_s
    started = time.monotonic()
    states: list[dict] = []
    ended = False
    while time.monotonic() < deadline:
        state = dict(await j.cdp.evaluate(_FACE_STATE) or {})
        if not states or {k: v for k, v in states[-1].items() if k != "t"} != state:
            states.append({**state, "t": round(time.monotonic() - started, 1)})
        turns = list(await j.cdp.evaluate("window.__gagosTurns || []") or [])
        frames = [f for t in turns for f in t.get("frames", [])]
        if any(f.get("event") in TERMINAL_FRAMES for f in frames):
            ended = True
            # The mirror's own terminal event follows the stream's; let it land.
            await asyncio.sleep(3)
            states.append({**dict(await j.cdp.evaluate(_FACE_STATE) or {}), "t": "end"})
            break
        await asyncio.sleep(1)
    turns = list(await j.cdp.evaluate("window.__gagosTurns || []") or [])
    return {"turns": turns, "states": states, "ended": ended}


def frame_counts(turns: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for turn in turns:
        for frame in turn.get("frames", []):
            counts[frame.get("event", "?")] = counts.get(frame.get("event", "?"), 0) + 1
    return counts


async def ask_01(j: Journey) -> None:
    """UX-01 (4) and INT-02 (3): one request the operator sends, correlated
    from his send through the backend's own events to its terminal event, an
    honest receipt and the being back at rest. The runner never sends."""
    r = j.record
    r.boundary = (
        "The operator typed and sent the request himself; the runner only "
        "watched. Frames are kept by type, size and turn_id, never their text, "
        "and no operator id, token or file content is recorded. UX-01 and "
        "INT-02 earn points only signed in, headed, on the named desktop and "
        "the build that ships, with this record committed; a pending decision "
        "here is recorded, not judged (decide-01 judges it)."
    )
    if not r.step(
        "controls ready",
        await j.wait_for(f"document.querySelector('{CONTROLS_READY}')", 60),
    ):
        return
    if not r.step(
        "signed in",
        await j.signed_in(),
        "the operator signs in himself, in this window (tools/gagos_journeys.py open)",
    ):
        return
    await body_drawn(j, "the 3D body is drawn", within=20)
    say("ready: type ONE small request into the composer and press Enter yourself.")
    say(f"I watch for up to {WATCH_LIMIT_S // 60} minutes and never send anything.")
    seen = await watch_turn(j)
    await j.collect()
    turns, states = seen["turns"], seen["states"]
    frames = [f for t in turns for f in t.get("frames", [])]
    counts = frame_counts(turns)
    r.measured["frames by type"] = counts
    r.measured["face states"] = [
        f"{s['t']}: working={s.get('working')} phase={s.get('phase')} "
        f"task={s.get('taskState')} approval={s.get('approval')} "
        f"receipts={','.join(s.get('receipts') or []) or '-'} draft={s.get('draft')}"
        for s in states
    ]
    r.step(
        "one request, sent by the operator",
        len(r.work_requests) == 1 and len(turns) == 1,
        f"{len(r.work_requests)} work request(s); {len(turns)} turn stream(s)",
    )
    ids = sorted({f["turnId"] for f in frames if f.get("turnId")})
    turn_id = ids[0] if len(ids) == 1 else None
    r.step("one turn", turn_id is not None, f"{len(ids)} turn id(s) in its stream")
    mirror = mirror_events(j.cdp.events)
    mine = [m for m in mirror if turn_id and m["turnId"] == turn_id]
    started = [m for m in mine if m["type"] == "turn.started"]
    finished = [m for m in mine if m["type"] in ("turn.completed", "turn.failed")]
    r.measured["the backend's events for the turn"] = [
        f"{m['id']}: {m['type']}" for m in mine
    ] or "none seen"
    r.step(
        "the backend started it",
        len(started) == 1,
        f"turn.started as event {started[0]['id']}" if started else "no turn.started",
    )
    ended = seen["ended"]
    terminal = next(
        (f["event"] for f in reversed(frames) if f.get("event") in TERMINAL_FRAMES),
        None,
    )
    r.step(
        "it ended, on both channels",
        ended
        and len(finished) == 1
        and bool(started)
        and _after(finished[0]["id"], started[0]["id"]),
        (
            f"stream: {terminal}; mirror: {finished[0]['type']} as event {finished[0]['id']}"
            if finished
            else f"stream: {terminal or 'no terminal frame'}; mirror: no terminal event"
        ),
    )
    last = states[-1] if states else {}
    receipts = set(last.get("receipts") or [])
    honest = RECEIPTS_AFTER.get(terminal or "", set())
    r.step(
        "an honest receipt",
        bool(receipts) and receipts <= honest | {"unknown"} and bool(receipts & honest),
        f"shown: {', '.join(sorted(receipts)) or 'none'}; after {terminal or 'no end'}",
    )
    typed = any((s.get("draft") or 0) > 0 for s in states)
    r.step(
        "the draft left the composer when it was sent",
        typed and (last.get("draft") or 0) == 0,
        "a draft was typed, and the composer is empty after the turn"
        if typed
        else "no draft was seen being typed",
    )
    r.step(
        "at rest again",
        last.get("working") == "false",
        f"working={last.get('working')}",
    )
    await body_drawn(j, "the 3D body is drawn after the turn", within=5)
    if any(s.get("approval") for s in states):
        r.measured["a decision was asked"] = "yes (judged by decide-01)"


def _after(later: str, earlier: str) -> bool:
    try:
        return int(later) > int(earlier)
    except ValueError:
        return False


#: Phase 2's journeys: each is watched, never driven.
WATCHES: dict[str, tuple[str, str, Callable[[Journey], Awaitable[None]]]] = {
    "ask-01": (
        "UX-01 ask-to-result and INT-02 turn boundary",
        "Sign in first (open). When I say ready, type one small request and press Enter.",
        ask_01,
    ),
}


async def watch(
    watch_id: str,
    *,
    url: str,
    port: int,
    commit: str,
    browser: str,
    tree: str = "",
) -> JourneyRecord:
    """Attach to the open journey window, install the observers, reload once
    (before he types) so the turn probe and the mirror's stream are seen from
    the start, then run the watch."""
    import websockets

    criterion, _steps, body = WATCHES[watch_id]
    record = JourneyRecord(
        journey=watch_id,
        criterion=criterion,
        commit=commit,
        browser=browser,
        tree=tree,
        viewport="as the operator has it",
        url=url,
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    async with websockets.connect(page_socket(port, url), max_size=None) as socket:
        journey = Journey(Cdp(socket), record)
        await journey.start()
        await journey.cdp.send(
            "Page.addScriptToEvaluateOnNewDocument", source=_TURN_PROBE
        )
        await journey.cdp.send("Page.reload")
        await asyncio.sleep(1)
        try:
            await body(journey)
        except JourneyRefused as exc:
            record.step("refused", False, str(exc))
    return record.finish()


# ------------------------------------------------------------------ the commands


def served_tree(url: str) -> Path | None:
    """The checkout whose frontend serves *url*: the local process listening
    on its port, read from its command line (Vite's dev and preview servers run
    from <checkout>/frontend/node_modules; the face that ships is served by
    <checkout>/tools/shipping_face.py). None when it cannot be told."""
    try:
        import psutil
    except ImportError:
        return None
    port = urllib.parse.urlsplit(url).port
    try:
        processes = [
            psutil.Process(c.pid)
            for c in psutil.net_connections(kind="tcp")
            if c.status == psutil.CONN_LISTEN
            and c.laddr
            and c.laddr.port == port
            and c.pid
        ]
        commands = [(p.cmdline(), p.cwd()) for p in processes]
    except psutil.Error:
        return None
    for command, cwd in commands:
        for part in command:
            norm = part.replace("\\", "/").lower()
            at = norm.find("/frontend/node_modules/")
            if at > 0:
                return Path(part[:at])
            if norm.endswith("tools/shipping_face.py"):
                script = Path(part)
                if not script.is_absolute():
                    script = Path(cwd) / script
                return script.resolve().parents[1]
    return None


def served_commit(url: str) -> tuple[str, str]:
    """The commit the face at *url* is served from, and its tree: the path and
    whether its frontend has uncommitted changes. 2026-11-15: the runner first
    pinned its own checkout, a different commit from the one serving the face."""
    tree = served_tree(url)
    if tree is None:
        return "unknown", "the tree serving the face could not be found"

    def git(*args: str) -> str:
        return subprocess.run(  # noqa: S603 - fixed argv
            ["git", "-C", str(tree), *args],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()

    head = git("rev-parse", "HEAD") or "unknown"
    dirty = git("status", "--porcelain", "--", "frontend")
    return head, f"{tree}, frontend {'with uncommitted changes' if dirty else 'clean'}"


def _browser(port: int) -> str:
    with urllib.request.urlopen(  # noqa: S310 - 127.0.0.1, a fixed path
        f"http://127.0.0.1:{port}/json/version", timeout=10
    ) as response:
        return json.loads(response.read().decode("utf-8")).get("Browser", "Chrome")


def cmd_open(args: argparse.Namespace) -> int:
    profile = eye.profile("journey")
    (profile / "DevToolsActivePort").unlink(missing_ok=True)
    subprocess.Popen(launch_argv(args.url, profile))  # noqa: S603 - checked URL
    port = devtools_port(profile)
    print(
        f"GAGOS's journey window is open on {args.url} (DevTools 127.0.0.1:{port}). "
        "Sign in there yourself, then run: python tools/gagos_journeys.py run <id>"
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if args.journey not in JOURNEYS:
        print(f"no journey {args.journey!r}; see: python tools/gagos_journeys.py list")
        return 2
    profile = eye.profile("journey")
    try:
        port = devtools_port(profile, timeout_s=2)
    except JourneyRefused:
        print("the journey window is not open: python tools/gagos_journeys.py open")
        return 2
    commit, tree = served_commit(args.url)
    record = asyncio.run(
        run(
            args.journey,
            url=args.url,
            port=port,
            commit=commit,
            tree=tree,
            browser=_browser(port),
        )
    )
    path = write_record(record)
    print(f"{args.journey}: {record.outcome}; evidence: {path}")
    return 0 if record.outcome == "passed" else 1


def cmd_watch(args: argparse.Namespace) -> int:
    """Phase 2: the operator does the steps it prints, in the open journey
    window; the runner watches and writes the record."""
    if args.journey not in WATCHES:
        print(f"no watch {args.journey!r}; see: python tools/gagos_journeys.py list")
        return 2
    profile = eye.profile("journey")
    try:
        port = devtools_port(profile, timeout_s=2)
    except JourneyRefused:
        print("the journey window is not open: python tools/gagos_journeys.py open")
        return 2
    criterion, steps, _body = WATCHES[args.journey]
    say(f"{args.journey}: {criterion}")
    say(steps)
    commit, tree = served_commit(args.url)
    record = asyncio.run(
        watch(
            args.journey,
            url=args.url,
            port=port,
            commit=commit,
            tree=tree,
            browser=_browser(port),
        )
    )
    path = write_record(record)
    print(f"{args.journey}: {record.outcome}; evidence: {path}")
    return 0 if record.outcome == "passed" else 1


def cmd_list(_args: argparse.Namespace) -> int:
    for key, (criterion, _body) in JOURNEYS.items():
        print(f"{key}: {criterion} (run: the runner drives, nothing is sent)")
    for key, (criterion, _steps, _body) in WATCHES.items():
        print(f"{key}: {criterion} (watch: you send, the runner measures)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    opened = sub.add_parser("open")
    opened.add_argument("--url", default=FACE_URL)
    opened.set_defaults(func=cmd_open)
    ran = sub.add_parser("run")
    ran.add_argument("journey")
    ran.add_argument("--url", default=FACE_URL)
    ran.set_defaults(func=cmd_run)
    watched = sub.add_parser("watch")
    watched.add_argument("journey")
    watched.add_argument("--url", default=FACE_URL)
    watched.set_defaults(func=cmd_watch)
    listed = sub.add_parser("list")
    listed.set_defaults(func=cmd_list)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
