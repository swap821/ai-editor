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


def shot_argv(url: str, out: Path, *, size: str, wait_ms: int) -> list[str]:
    width, height = (int(x) for x in size.lower().split("x"))
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
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    run(
        shot_argv(url, out, size=size, wait_ms=wait_ms),
        capture_output=True,
        timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if not out.is_file() or out.stat().st_size == 0:
        raise EyeUnavailable(f"Chrome produced no screenshot of {url}")
    return out


def window_argv(url: str) -> list[str]:
    return [
        chrome(),
        f"--user-data-dir={profile('window')}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        url,
    ]


def cmd_window(args: argparse.Namespace) -> int:
    subprocess.Popen(window_argv(args.url))  # noqa: S603 - fixed argv
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
