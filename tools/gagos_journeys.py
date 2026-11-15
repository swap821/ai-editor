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
import re
import subprocess
import sys
import time
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
EVIDENCE_DIR = REPO / "docs" / "frontend" / "evidence" / "journeys"
#: The composer and the scene, as the face marks them (SuperbrainApp.jsx).
COMPOSER = '[aria-label="Talk to GAGOS"]'
CANVAS = ".scene-layer canvas"
CONTROLS_READY = '[data-controls-ready="true"]'
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
    steps: list[Step] = field(default_factory=list)
    work_requests: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)
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
            f"Run {self.started_at} on commit `{self.commit[:12]}`, {self.browser}, "
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
            "fetch('/api/v1/auth/session', {credentials: 'include'})"
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
    dropping; the view restores once; nothing is sent twice (here: nothing at
    all, since the draft is never sent)."""
    r = j.record
    r.boundary = (
        "A draft only, with no live work in flight: this proves the draft, the "
        "single measured restore and that no work request was sent across a "
        "graphics-context loss and a network drop. It does not prove a pending "
        "decision or a receipt surviving them during real work, which REC-01's "
        "full threshold also needs; REC-01 earns no points from this run alone."
    )
    if not r.step(
        "controls ready",
        await j.wait_for(f"document.querySelector('{CONTROLS_READY}')", 60),
    ):
        return
    await j.signed_in()
    draft = f"journey draft {int(time.time())}"
    await j.type_into(COMPOSER, draft)
    r.step("draft typed", await j.value_of(COMPOSER) == draft)
    lost = await j.cdp.evaluate(
        "(() => { const c = document.querySelector('" + CANVAS + "');"
        " const gl = c && (c.getContext('webgl2') || c.getContext('webgl'));"
        " const ext = gl && gl.getExtension('WEBGL_lose_context');"
        " if (!ext) return false; window.__gagosJourneyLoss = ext;"
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
    restored = await j.wait_for(
        "(window.__gagosJourney.metrics || []).some(m => m.name === 'context-recovery')",
        20,
    )
    count = sum(1 for m in await j.metrics() if m.get("name") == "context-recovery")
    r.step("restored once", restored and count == 1, f"{count} measured restore(s)")
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
    back = await j.wait_for(f"document.querySelector('{CONTROLS_READY}')", 60)
    r.step("draft back after a reload", back and await j.value_of(COMPOSER) == draft)
    await j.collect()
    r.step("no work request sent", not r.work_requests, f"{len(r.work_requests)} sent")


JOURNEYS: dict[str, tuple[str, Callable[[Journey], Awaitable[None]]]] = {
    "rec-01": ("REC-01 renderer and backend recovery", rec_01),
}


async def run(
    journey_id: str, *, url: str, port: int, commit: str, browser: str
) -> JourneyRecord:
    import websockets

    criterion, body = JOURNEYS[journey_id]
    record = JourneyRecord(
        journey=journey_id,
        criterion=criterion,
        commit=commit,
        browser=browser,
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


# ------------------------------------------------------------------ the commands


def _commit() -> str:
    return (
        subprocess.run(  # noqa: S603 - fixed argv
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or "unknown"
    )


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
    record = asyncio.run(
        run(
            args.journey,
            url=args.url,
            port=port,
            commit=_commit(),
            browser=_browser(port),
        )
    )
    path = write_record(record)
    print(f"{args.journey}: {record.outcome}; evidence: {path}")
    return 0 if record.outcome == "passed" else 1


def cmd_list(_args: argparse.Namespace) -> int:
    for key, (criterion, _body) in JOURNEYS.items():
        print(f"{key}: {criterion}")
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
    listed = sub.add_parser("list")
    listed.set_defaults(func=cmd_list)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
