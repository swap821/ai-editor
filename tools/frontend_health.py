#!/usr/bin/env python
"""Frontend health detector (CRW Phase 0).

The read-only "objective battery" for the Continuous Renovation Worker
(``docs/superpowers/specs/2026-07-01-continuous-renovation-worker.md``). It runs the
machine-verifiable frontend checks that already exist in this repo, aggregates them
into an evidence-backed JSON findings report, and prints a scannable summary.

HONEST SCOPE (the whole point). This measures only MACHINE-VERIFIABLE axes — lint,
types, tests, build, bundle size, and the palette/CSS canon laws. It never judges
subjective beauty (no headless WebGL; the aesthetic call is the operator's ``:5173``
eye). A check it cannot run (missing tool/dep) is reported ``unavailable`` — never
faked, never silently skipped.

This is a REPORTER, not a gate: it exits 0 even when checks fail, so it is safe to
run unattended (GREEN / plan-only per AGENTS.md §VII.3). Pass ``--gate`` to make it
exit non-zero on any failure (for CI use).

Usage:
  python tools/frontend_health.py                 # quick: lint + types + canon
  python tools/frontend_health.py --full          # + tests + build + bundle size
  python tools/frontend_health.py --json PATH      # write report (default .aios/state/FRONTEND_HEALTH.json)
  python tools/frontend_health.py --gate           # exit 1 if any check failed
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND = REPO_ROOT / "frontend"
DEFAULT_OUT = REPO_ROOT / ".aios" / "state" / "FRONTEND_HEALTH.json"

# Status vocabulary (ordered worst→best for the roll-up).
FAIL, WARN, UNAVAILABLE, OK = "fail", "warn", "unavailable", "ok"
_SEVERITY = {FAIL: 3, WARN: 2, UNAVAILABLE: 1, OK: 0}


@dataclass
class CheckResult:
    """One objective check + its evidence. Evidence is a captured output tail."""

    name: str
    axis: str  # correctness | types | tests | build | canon | a11y
    status: str
    summary: str
    evidence: str = ""
    findings: list[str] = field(default_factory=list)
    duration_s: float = 0.0


def _run(cmd: list[str], *, cwd: Path, timeout: int) -> tuple[int | None, str]:
    """Run a subprocess read-only; return (returncode, combined-output-tail).

    returncode is None when the tool is missing / timed out — the caller maps that
    to ``unavailable`` rather than a false pass or fail.
    """
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return None, f"tool not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s: {' '.join(cmd)}"
    out = (proc.stdout or "") + (proc.stderr or "")
    tail = "\n".join(out.strip().splitlines()[-40:])
    return proc.returncode, tail


def _npm() -> str | None:
    """Resolve the npm executable cross-platform (npm / npm.cmd)."""
    return shutil.which("npm") or shutil.which("npm.cmd")


def _npm_check(name: str, axis: str, script: str, *, timeout: int) -> CheckResult:
    start = time.monotonic()
    npm = _npm()
    if npm is None:
        return CheckResult(name, axis, UNAVAILABLE, "npm not on PATH")
    if not (FRONTEND / "node_modules").is_dir():
        return CheckResult(
            name, axis, UNAVAILABLE,
            "frontend/node_modules missing — run `cd frontend; npm install`",
        )
    rc, tail = _run([npm, "run", script], cwd=FRONTEND, timeout=timeout)
    dur = round(time.monotonic() - start, 1)
    if rc is None:
        return CheckResult(name, axis, UNAVAILABLE, tail, duration_s=dur)
    if rc == 0:
        return CheckResult(name, axis, OK, f"`npm run {script}` clean", tail[-600:], duration_s=dur)
    return CheckResult(
        name, axis, FAIL, f"`npm run {script}` exited {rc}", tail[-2000:],
        findings=[f"{name}: non-zero exit ({rc}) — see evidence"], duration_s=dur,
    )


def _canon_check(name: str, script: Path, args: list[str]) -> CheckResult:
    start = time.monotonic()
    if not script.exists():
        return CheckResult(name, "canon", UNAVAILABLE, f"missing {script.name}")
    rc, tail = _run([sys.executable, str(script), *args], cwd=REPO_ROOT, timeout=120)
    dur = round(time.monotonic() - start, 1)
    if rc is None:
        return CheckResult(name, "canon", UNAVAILABLE, tail, duration_s=dur)
    if rc == 0:
        return CheckResult(name, "canon", OK, f"{script.name} clean", tail[-600:], duration_s=dur)
    return CheckResult(
        name, "canon", FAIL, f"{script.name} reported violations (exit {rc})",
        tail[-2000:], findings=[f"{name}: canon violation — see evidence"], duration_s=dur,
    )


def _bundle_size() -> CheckResult:
    """Report built JS/CSS bundle size from frontend/dist (post-build)."""
    dist = FRONTEND / "dist"
    if not dist.is_dir():
        return CheckResult(
            "bundle-size", "build", UNAVAILABLE,
            "no frontend/dist — run with --full (needs a build first)",
        )
    assets = list(dist.rglob("*.js")) + list(dist.rglob("*.css"))
    total = sum(a.stat().st_size for a in assets)
    biggest = sorted(assets, key=lambda a: a.stat().st_size, reverse=True)[:5]
    evidence = "\n".join(
        f"{a.relative_to(dist)}  {a.stat().st_size // 1024} KB" for a in biggest
    )
    total_kb = total // 1024
    # Advisory budget only — a WARN prompt to look, never a hard fail (no baseline yet).
    status = WARN if total_kb > 3000 else OK
    return CheckResult(
        "bundle-size", "build", status,
        f"{total_kb} KB across {len(assets)} JS/CSS assets"
        + (" (over 3 MB advisory budget)" if status == WARN else ""),
        evidence,
    )


def collect(full: bool) -> list[CheckResult]:
    """Run the battery. Quick = lint+types+canon; full adds tests+build+bundle."""
    checks: list[CheckResult] = [
        _npm_check("eslint", "correctness", "lint", timeout=180),
        _npm_check("typecheck", "types", "typecheck", timeout=180),
        _canon_check("css-canon", REPO_ROOT / "tools" / "check_css_canon.py", []),
        _canon_check("canon-frozen", REPO_ROOT / "tools" / "check_canon_frozen.py", []),
        # a11y is an open decision (spec §9.3): no eslint-jsx-a11y / axe wired yet.
        CheckResult(
            "a11y-static", "a11y", UNAVAILABLE,
            "no eslint-jsx-a11y configured — spec §9.3 open decision (recommend static-first)",
        ),
    ]
    if full:
        checks.append(_npm_check("vitest", "tests", "test", timeout=300))
        checks.append(_npm_check("build", "build", "build", timeout=300))
        checks.append(_bundle_size())
    return checks


def summarize(checks: list[CheckResult]) -> dict[str, Any]:
    """Pure roll-up (unit-tested): overall status + counts + flat findings list."""
    by_status: dict[str, int] = {OK: 0, WARN: 0, UNAVAILABLE: 0, FAIL: 0}
    findings: list[str] = []
    worst = OK
    for c in checks:
        by_status[c.status] = by_status.get(c.status, 0) + 1
        findings.extend(c.findings)
        if _SEVERITY[c.status] > _SEVERITY[worst]:
            worst = c.status
    return {
        "overall": worst,
        "counts": by_status,
        "actionable_findings": findings,
        "n_checks": len(checks),
    }


def _print_summary(report: dict[str, Any]) -> None:
    s = report["summary"]
    icon = {OK: "[OK]", WARN: "[WARN]", UNAVAILABLE: "[--]", FAIL: "[FAIL]"}
    print(f"\nFrontend health — overall: {s['overall'].upper()}")
    print(
        f"  ok={s['counts'][OK]}  warn={s['counts'][WARN]}  "
        f"unavailable={s['counts'][UNAVAILABLE]}  fail={s['counts'][FAIL]}\n"
    )
    for c in report["checks"]:
        print(f"  {icon.get(c['status'], '[?]'):7} {c['axis']:11} {c['name']:14} {c['summary']}")
    if s["actionable_findings"]:
        print("\n  Actionable findings (evidence-backed):")
        for f in s["actionable_findings"]:
            print(f"    - {f}")
    print()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Frontend health detector (CRW P0)")
    ap.add_argument("--full", action="store_true", help="also run tests + build + bundle size")
    ap.add_argument("--json", type=Path, default=DEFAULT_OUT, help="report output path")
    ap.add_argument("--gate", action="store_true", help="exit 1 if any check failed")
    args = ap.parse_args(argv)

    checks = collect(full=args.full)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "mode": "full" if args.full else "quick",
        "checks": [asdict(c) for c in checks],
        "summary": summarize(checks),
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _print_summary(report)
    print(f"  report → {args.json.relative_to(REPO_ROOT)}")

    if args.gate and report["summary"]["overall"] == FAIL:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
