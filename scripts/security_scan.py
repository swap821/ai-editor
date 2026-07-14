"""Small, dependency-free tracked-source secret scan for release CI.

The application already has a runtime redaction scanner.  This check covers a
different boundary: credentials accidentally committed to production source,
container definitions, or workflow configuration.  Test fixtures are excluded
because they intentionally contain synthetic tokens used to exercise redaction.
The scanner reports paths and line numbers only; it never prints the matched
value.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


_DEFAULT_ROOTS = (
    Path("aios"),
    Path("frontend/src"),
    Path("Dockerfile"),
    Path("Dockerfile.executor"),
    Path("Dockerfile.frontend"),
    Path("docker-compose.yml"),
    Path("gateway"),
    Path("gagos"),
    Path("gagos.cmd"),
    Path(".github/workflows"),
)
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:ghp|github_pat|glpat)_[A-Za-z0-9_\-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9_\-]{20,}\b")),
    ("openai-or-anthropic-key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}\b")),
    (
        "assigned-secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key)\s*"
            r"[:=]\s*['\"][^'\"]{16,}['\"]"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    line: int
    kind: str


def _tracked_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [Path(raw) for raw in result.stdout.decode("utf-8").split("\0") if raw]


def _files_under(roots: Iterable[Path]) -> list[Path]:
    tracked = _tracked_files()
    if not tracked:
        tracked = [path for path in Path.cwd().rglob("*") if path.is_file()]
    resolved_roots = [root for root in roots]
    selected: list[Path] = []
    for path in tracked:
        if any(path == root or root in path.parents for root in resolved_roots):
            selected.append(path)
    return sorted(set(selected))


def scan(roots: Iterable[Path] = _DEFAULT_ROOTS) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for path in _files_under(roots):
        absolute = path.resolve()
        try:
            raw = absolute.read_bytes()
        except OSError:
            continue
        if len(raw) > 2 * 1024 * 1024 or b"\0" in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in _PATTERNS:
                if pattern.search(line):
                    findings.append(Finding(path.as_posix(), line_number, kind))
    return tuple(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable findings"
    )
    args = parser.parse_args(argv)
    findings = scan()
    if args.json:
        import json

        print(json.dumps([asdict(finding) for finding in findings], sort_keys=True))
    else:
        for finding in findings:
            print(f"{finding.path}:{finding.line}: {finding.kind}")
    if findings:
        print("tracked-source secret scan failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
