#!/usr/bin/env python3
"""GAGOS's eye: its own Chrome, with its own profiles, apart from the operator's.

Operator, 2026-10-30: "for eye give a permanent solution (a personal Google
Chrome window for GAGOS)". GAGOS could not see what it builds; this is how it
starts to.

  window [--url URL]   open GAGOS's own Chrome window (its own profile, never
                       the operator's), by default on the frontend at :5173
  shot --url URL --out PNG [--size 1440x900] [--wait-ms 6000]
                       a headless screenshot through GAGOS's other profile (a
                       Chrome profile can serve one instance at a time, so the
                       window and the screenshots each have their own)

Profiles live in <AIOS_DATA_DIR>/gagos_eye/. Nothing here signs in anywhere.
What the eye does NOT do yet, honestly: judge. Its screenshots are evidence
for the reviewers and the operator; a visual check in the daily loop (before /
after, judged against his written UI laws) is the next step.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from aios import config  # noqa: E402

DEFAULT_URL = "http://127.0.0.1:5173/"
_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
)


class EyeUnavailable(RuntimeError):
    """GAGOS cannot see: no Chrome, or Chrome produced nothing."""


def chrome() -> str:
    for path in _CANDIDATES:
        if path.is_file():
            return str(path)
    found = shutil.which("chrome") or shutil.which("google-chrome")
    if found:
        return found
    raise EyeUnavailable("Google Chrome is not installed")


def profile(kind: str) -> Path:
    """GAGOS's own profile directory: ``window`` or ``shot``."""
    path = config.DATA_DIR / "gagos_eye" / f"{kind}-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def page_url(url: str) -> str:
    """An http(s) page, nothing else: text that Chrome would read as one of
    its own switches (``--user-data-dir=...``) is refused before any process
    starts (Codex's post-merge review of #566)."""
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    if url.startswith("-") or parts.scheme not in ("http", "https") or not parts.netloc:
        raise EyeUnavailable(f"not a page GAGOS may open: {url!r}")
    return url


def shot_argv(url: str, out: Path, *, size: str, wait_ms: int) -> list[str]:
    url = page_url(url)
    try:
        width, height = (int(x) for x in size.lower().split("x"))
    except ValueError as exc:
        raise EyeUnavailable(f"not a window size: {size!r}") from exc
    return [
        chrome(),
        "--headless=new",
        f"--user-data-dir={profile('shot')}",
        "--no-first-run",
        "--no-default-browser-check",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        f"--virtual-time-budget={wait_ms}",
        f"--screenshot={out}",
        url,
    ]


def shot(
    url: str,
    out: Path,
    *,
    size: str = "1440x900",
    wait_ms: int = 6000,
    run=subprocess.run,
) -> Path:
    """Capture *url* to *out*. The capture goes to its own file first and
    replaces *out* only when Chrome exited 0 and left something in it: a
    failed look never destroys the last one (Codex's reviews of #566 and
    #567)."""
    out = Path(out).resolve()
    capture = out.with_name(f"{out.stem}.capturing{out.suffix}")
    argv = shot_argv(url, capture, size=size, wait_ms=wait_ms)  # validates first
    out.parent.mkdir(parents=True, exist_ok=True)
    capture.unlink(missing_ok=True)
    try:
        try:
            proc = run(
                argv,
                capture_output=True,
                timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EyeUnavailable(f"Chrome did not finish: {exc}") from exc
        code = getattr(proc, "returncode", None)
        if code != 0:
            raise EyeUnavailable(f"Chrome exited {code} on {url}")
        if not capture.is_file() or capture.stat().st_size == 0:
            raise EyeUnavailable(f"Chrome produced no screenshot of {url}")
        os.replace(capture, out)
    finally:
        capture.unlink(missing_ok=True)
    return out


def window_argv(url: str) -> list[str]:
    url = page_url(url)
    return [
        chrome(),
        f"--user-data-dir={profile('window')}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        url,
    ]


def cmd_window(args: argparse.Namespace) -> int:
    try:
        argv = window_argv(args.url)
    except EyeUnavailable as exc:
        print(f"GAGOS cannot see: {exc}")
        return 2
    subprocess.Popen(argv)  # noqa: S603 - fixed argv, a checked URL
    print(f"GAGOS's own Chrome window: {args.url} (profile {profile('window')})")
    return 0


def cmd_shot(args: argparse.Namespace) -> int:
    try:
        out = shot(args.url, Path(args.out), size=args.size, wait_ms=args.wait_ms)
    except EyeUnavailable as exc:
        print(f"GAGOS cannot see: {exc}")
        return 2
    print(f"saw {args.url}: {out} ({out.stat().st_size} bytes)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    w = sub.add_parser("window")
    w.add_argument("--url", default=DEFAULT_URL)
    w.set_defaults(func=cmd_window)
    s = sub.add_parser("shot")
    s.add_argument("--url", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--size", default="1440x900")
    s.add_argument("--wait-ms", type=int, default=6000)
    s.set_defaults(func=cmd_shot)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
