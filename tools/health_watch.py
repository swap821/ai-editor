#!/usr/bin/env python3
"""Health watch: notice what breaks while nobody is looking, fix what is safe, tell the operator.

Personal-dependability items 2 and 3 (operator, 2026-10-12): Ollama went down
mid-session and nobody knew; nightly CI failures went unseen for five days.
`doctor` reports both when asked, and nothing asks.

One run (``--once``; a scheduled task runs it every 30 minutes):

* **Ollama.** The same check `doctor` makes (``OllamaClient().list_models()``
  against ``config.OLLAMA_HOST``). If it is down, start it -- the same
  ``ollama app.exe`` the operator's Startup shortcut launches, or ``ollama
  serve`` when only the CLI is installed -- wait, check again, and report the
  outcome either way. A restart that did not bring it back is an alert, not a
  silence.
* **CI on master.** ``gh run list`` for master. A workflow whose LATEST completed
  run FAILED (failure, timed out, startup failure) -- master is red right now --
  is reported ONCE per failed run;
  the reported run ids persist in a state file, so a red nightly is one alert,
  not one every half hour.
* **Notify.** A Windows notification for anything that needs him, and one
  JSON line per run in the log either way -- the log is the record, the
  notification is only the doorbell.

Nothing here changes the repository, a ledger, a model, or a key. The only
side effect besides the log and state file is starting Ollama, which the
operator already runs at every login.

    python tools/health_watch.py --once            # check, fix what is safe, notify
    python tools/health_watch.py --once --quiet    # same, no notification (log only)
    python tools/health_watch.py --print-task      # the scheduled-task command, for the operator to run
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: GitHub conclusions that mean "this broke", as opposed to cancelled/skipped.
FAILED_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure"})
#: Reported run ids kept in the state file; older ones age out.
STATE_KEEP = 500
#: On the first run, failures older than this are recorded as seen, not alerted.
FIRST_RUN_LOOKBACK_H = 24.0
#: How long a started Ollama gets to answer before the restart counts as failed.
OLLAMA_START_WAIT_S = 45.0


def _default_data_dir() -> Path:
    from aios import config

    return Path(config.DATA_DIR) / "health_watch"


@dataclass
class Finding:
    """One thing the operator should know about."""

    kind: str  # "ollama" | "ci"
    title: str
    detail: str


@dataclass
class RunReport:
    ts: str
    ollama: dict = field(default_factory=dict)
    ci: dict = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Ollama
# --------------------------------------------------------------------------- #
def ollama_available() -> tuple[bool, int]:
    """(reachable, installed model count) -- doctor's own check."""
    from aios.core.llm import OllamaClient

    listing = OllamaClient().list_models()
    return bool(listing.get("available")), len(listing.get("models") or ())


def ollama_launch_command() -> Optional[list[str]]:
    """How to start Ollama here, or None when it is not installed."""
    install = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama"
    tray = install / "ollama app.exe"
    if tray.is_file():
        return [str(tray)]
    cli = shutil.which("ollama") or (
        str(install / "ollama.exe") if (install / "ollama.exe").is_file() else None
    )
    return [cli, "serve"] if cli else None


def start_ollama(command: list[str]) -> None:
    """Start Ollama detached, so it outlives this check."""
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(  # noqa: S603 - a fixed, installed binary; no shell, no input
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )


def check_ollama(
    *,
    probe: Callable[[], tuple[bool, int]] = ollama_available,
    launch_command: Callable[[], Optional[list[str]]] = ollama_launch_command,
    start: Callable[[list[str]], None] = start_ollama,
    sleep: Callable[[float], None] = time.sleep,
    wait_s: float = OLLAMA_START_WAIT_S,
) -> tuple[dict, list[Finding]]:
    """Check Ollama; if it is down, start it once and check again."""
    try:
        up, models = probe()
    except Exception as exc:  # noqa: BLE001 - unreachable is a result, not a crash
        up, models = False, 0
        first_error = str(exc)
    else:
        first_error = ""
    if up:
        return {"up": True, "models": models, "action": "none"}, []

    command = launch_command()
    if command is None:
        return (
            {"up": False, "action": "not_installed", "error": first_error},
            [
                Finding(
                    "ollama",
                    "Ollama is down and not installed",
                    "No Ollama install was found, so it could not be restarted.",
                )
            ],
        )
    try:
        start(command)
    except OSError as exc:
        return (
            {"up": False, "action": "start_failed", "error": str(exc)},
            [Finding("ollama", "Ollama is down; restart failed", str(exc))],
        )

    waited = 0.0
    while waited < wait_s:
        sleep(3.0)
        waited += 3.0
        try:
            up, models = probe()
        except Exception:  # noqa: BLE001
            up = False
        if up:
            return (
                {
                    "up": True,
                    "models": models,
                    "action": "restarted",
                    "waited_s": waited,
                },
                [
                    Finding(
                        "ollama",
                        "Ollama was down -- restarted",
                        f"It answered again after {waited:.0f}s with {models} model(s).",
                    )
                ],
            )
    return (
        {"up": False, "action": "restart_did_not_answer", "waited_s": waited},
        [
            Finding(
                "ollama",
                "Ollama is down; restart did not bring it back",
                f"Started {Path(command[0]).name}; no answer after {waited:.0f}s.",
            )
        ],
    )


# --------------------------------------------------------------------------- #
# CI
# --------------------------------------------------------------------------- #
def gh_master_runs(limit: int = 30) -> list[dict]:
    """Recent workflow runs on master, from the GitHub CLI."""
    out = subprocess.run(  # noqa: S603, S607 - fixed argv, no shell
        [
            "gh",
            "run",
            "list",
            "--branch",
            "master",
            "--limit",
            str(limit),
            "--json",
            "databaseId,workflowName,conclusion,status,createdAt,url,headSha",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(out.stdout or "[]")


def _age_hours(created_at: str, now: datetime) -> float:
    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return 0.0  # unparseable: treat as recent, so it is reported, not hidden
    return (now - created).total_seconds() / 3600.0


def check_ci(
    reported: set[int],
    *,
    runs: Callable[[], list[dict]] = gh_master_runs,
    first_run: bool = False,
    now: Optional[datetime] = None,
) -> tuple[dict, list[Finding], set[int]]:
    """New failed runs on master, each reported once.

    On the FIRST run (no state yet) only failures from the last
    ``FIRST_RUN_LOOKBACK_H`` hours are reported; older ones are recorded as seen
    without a notification, so installing the watch does not replay weeks of
    history as a burst of alerts.
    """
    try:
        listing = runs()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        # Not being able to look is itself worth one line in the log, but not a
        # notification every half hour: gh may simply be logged out.
        return {"checked": False, "error": str(exc)[:300]}, [], reported
    # Only a workflow's LATEST completed run says whether master is red NOW. A
    # failure a later green run already superseded is history, not an alert
    # (first live run, 2026-10-19: it reported #504's squash failure, which #506
    # had fixed the same day). `gh run list` returns newest first.
    latest: dict[str, dict] = {}
    for r in listing:
        if r.get("status") == "completed":
            latest.setdefault(str(r.get("workflowName", "?")), r)
    failed = [r for r in latest.values() if r.get("conclusion") in FAILED_CONCLUSIONS]
    new = [r for r in failed if int(r["databaseId"]) not in reported]
    baseline: list[dict] = []
    if first_run:
        moment = now or datetime.now(timezone.utc)
        baseline = [
            r
            for r in new
            if _age_hours(r.get("createdAt", ""), moment) > FIRST_RUN_LOOKBACK_H
        ]
        new = [r for r in new if r not in baseline]
    findings = [
        Finding(
            "ci",
            f"CI failed on master: {r.get('workflowName', '?')}",
            f"{r.get('conclusion')} at {str(r.get('headSha', ''))[:8]} "
            f"({str(r.get('createdAt', ''))[:16]}Z) {r.get('url', '')}",
        )
        for r in new
    ]
    updated = reported | {int(r["databaseId"]) for r in new + baseline}
    return (
        {
            "checked": True,
            "runs": len(listing),
            "failed": len(failed),
            "new": len(new),
            "baselined": len(baseline),
        },
        findings,
        updated,
    )


# --------------------------------------------------------------------------- #
# Notify + state
# --------------------------------------------------------------------------- #
def windows_toast(title: str, body: str) -> bool:
    """Show a Windows notification. False when it could not be shown."""
    if os.name != "nt":
        return False
    xml = (
        '<toast><visual><binding template="ToastGeneric">'
        f"<text>{escape(title)}</text><text>{escape(body)}</text>"
        "</binding></visual></toast>"
    ).replace("'", "''")
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
        " ContentType = WindowsRuntime] > $null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument,"
        " ContentType = WindowsRuntime] > $null;"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$x.LoadXml('{xml}');"
        "$t = [Windows.UI.Notifications.ToastNotification]::new($x);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        r"'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'"
        ").Show($t)"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        result = subprocess.run(  # noqa: S603, S607 - fixed argv, no shell
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                encoded,
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def load_reported(state_path: Path) -> set[int]:
    try:
        return {
            int(x)
            for x in json.loads(state_path.read_text(encoding="utf-8"))["reported_ci"]
        }
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def save_reported(state_path: Path, reported: set[int]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    keep = sorted(reported)[-STATE_KEEP:]
    state_path.write_text(json.dumps({"reported_ci": keep}) + "\n", encoding="utf-8")


def run_once(
    *,
    data_dir: Path,
    notify: Callable[[str, str], bool] = windows_toast,
    quiet: bool = False,
    ollama_check: Callable[[], tuple[dict, list[Finding]]] = check_ollama,
    ci_runs: Callable[[], list[dict]] = gh_master_runs,
) -> RunReport:
    """One watch cycle. Returns what it saw; writes the log and state."""
    state_path = data_dir / "state.json"
    report = RunReport(ts=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    report.ollama, ollama_findings = ollama_check()
    first_run = not state_path.exists()
    reported = load_reported(state_path)
    report.ci, ci_findings, reported = check_ci(
        reported, runs=ci_runs, first_run=first_run
    )
    report.findings = ollama_findings + ci_findings

    notified = []
    if not quiet:
        for finding in report.findings:
            notified.append(notify(finding.title, finding.detail))
    # The state is saved AFTER notifying: a run that died mid-way re-reports
    # rather than silently swallowing a failure it never showed anyone.
    save_reported(state_path, reported)

    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "health_watch.jsonl").open("a", encoding="utf-8") as log:
        log.write(
            json.dumps(
                {
                    "ts": report.ts,
                    "ollama": report.ollama,
                    "ci": report.ci,
                    "findings": [f.__dict__ for f in report.findings],
                    "notified": notified,
                }
            )
            + "\n"
        )
    return report


def task_command() -> str:
    """The Task Scheduler command that runs this every 30 minutes, as the operator."""
    python = Path(sys.executable).resolve()
    script = Path(__file__).resolve()
    action = f'\\"{python}\\" \\"{script}\\" --once'
    return (
        f'schtasks /Create /TN "GAGOS health watch" /SC MINUTE /MO 30 '
        f'/TR "{action}" /RL LIMITED /F'
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="run one watch cycle")
    parser.add_argument(
        "--quiet", action="store_true", help="log only, no notification"
    )
    parser.add_argument(
        "--print-task",
        action="store_true",
        help="print the scheduled-task command (creating it is the operator's act)",
    )
    args = parser.parse_args(argv)
    if args.print_task:
        print(task_command())
        return 0
    if not args.once:
        parser.print_help()
        return 2
    report = run_once(data_dir=_default_data_dir(), quiet=args.quiet)
    print(
        json.dumps(
            {
                "ollama": report.ollama,
                "ci": report.ci,
                "findings": [f.title for f in report.findings],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
