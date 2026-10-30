"""Static checks of frontend text with the project's own toolchain (2026-10-30).

GAGOS's daily frontend work (docs/learning/PAYOFF_PREREGISTRATION.md D14) judges a
proposed file BEFORE anyone has read it, so this module never executes the code
it judges. One node process, given ``{project-relative path: text}``, returns
for each text:

* ESLint's messages, from the project's own ``eslint.config.js`` through
  ``ESLint.lintText`` (the text is linted as if it were at its path, so the
  path's config and ignores apply, but nothing is written to disk);
* TypeScript's syntax diagnostics (``transpileModule``: parsing only, no types).

Linting parses code and runs the configured rules over it; it never runs the
code. The toolchain is ``frontend/node_modules`` of the project being judged;
without it every check refuses, so the absence of a tool is never a pass.

Also here: which frontend files the daily work may touch. Files the
lab-to-product port owns (``frontend/superbrain-source.json``) are excluded
until the lab and the product are reconciled (the operator's guard).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aios.maintenance.frontend_imports import frontend_files

#: The port's manifest, relative to the project root.
PORT_MANIFEST = "frontend/superbrain-source.json"
#: Where the port's managed files live, relative to the project root.
PORT_ROOT = "frontend/src/superbrain"

_SCRIPT = r"""
const path = require('path');
const fs = require('fs');
const frontend = process.argv[1];
const { ESLint } = require(path.join(frontend, 'node_modules', 'eslint'));
const ts = require(path.join(frontend, 'node_modules', 'typescript'));
(async () => {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const eslint = new ESLint({ cwd: frontend });
  const out = {};
  for (const [rel, text] of Object.entries(input.files)) {
    const filePath = path.join(input.root, rel);
    const results = await eslint.lintText(text, { filePath });
    const messages = (results[0] ? results[0].messages : []).map((m) => ({
      rule: m.ruleId || null, severity: m.severity, line: m.line || 0,
      column: m.column || 0, message: m.message, fatal: !!m.fatal,
    }));
    const parsed = ts.transpileModule(text, { fileName: filePath, reportDiagnostics: true,
      compilerOptions: { jsx: ts.JsxEmit.ReactJSX, allowJs: true } });
    const parse = (parsed.diagnostics || []).map((d) => ts.flattenDiagnosticMessageText(d.messageText, ' '));
    out[rel] = { messages, parse };
  }
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String((e && e.stack) || e)); process.exit(2); });
"""


class StaticCheckUnavailable(RuntimeError):
    """The project's frontend toolchain could not judge the text."""


@dataclass(frozen=True)
class LintMessage:
    rule: str | None
    severity: int
    line: int
    column: int
    message: str
    fatal: bool = False


@dataclass(frozen=True)
class StaticResult:
    """What the toolchain says about one text."""

    messages: tuple[LintMessage, ...]
    parse_errors: tuple[str, ...] = field(default=())

    def warnings(self, rule: str | None = None) -> list[LintMessage]:
        return [
            m
            for m in self.messages
            if m.severity == 1 and (rule is None or m.rule == rule)
        ]

    @property
    def errors(self) -> list[LintMessage]:
        return [m for m in self.messages if m.severity == 2 or m.fatal]


def check_texts(
    project_root: Path,
    texts: Mapping[str, str],
    *,
    run: Callable[..., Any] = subprocess.run,
    timeout_s: float = 600,
) -> dict[str, StaticResult]:
    """Lint and parse each text as if it were at its project-relative path."""
    if not texts:
        return {}
    root = Path(project_root).resolve()
    frontend = root / "frontend"
    node = shutil.which("node")
    for tool in ("eslint/package.json", "typescript/package.json"):
        if not (frontend / "node_modules" / tool).is_file():
            raise StaticCheckUnavailable(
                f"frontend toolchain missing ({tool}); run `npm ci` in {frontend}"
            )
    if node is None:
        raise StaticCheckUnavailable("node not found")
    payload = json.dumps({"root": str(root), "files": dict(texts)})
    try:
        proc = run(
            [node, "-e", _SCRIPT, str(frontend)],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(frontend),
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise StaticCheckUnavailable(
            f"static checks timed out after {timeout_s}s"
        ) from exc
    if proc.returncode != 0:
        raise StaticCheckUnavailable(
            f"static checks failed (exit {proc.returncode}): {(proc.stderr or '')[-800:]}"
        )
    try:
        raw = json.loads(proc.stdout or "{}")
    except ValueError as exc:
        raise StaticCheckUnavailable("static checks returned no JSON") from exc
    results: dict[str, StaticResult] = {}
    for rel in texts:
        entry = raw.get(rel)
        if not isinstance(entry, dict):
            raise StaticCheckUnavailable(f"static checks returned nothing for {rel}")
        results[rel] = StaticResult(
            messages=tuple(
                LintMessage(
                    rule=m.get("rule"),
                    severity=int(m.get("severity", 0)),
                    line=int(m.get("line", 0)),
                    column=int(m.get("column", 0)),
                    message=str(m.get("message", "")),
                    fatal=bool(m.get("fatal", False)),
                )
                for m in entry.get("messages", [])
            ),
            parse_errors=tuple(str(e) for e in entry.get("parse", [])),
        )
    return results


def port_managed(project_root: Path) -> frozenset[str]:
    """Project-relative paths the lab-to-product port owns. An unreadable
    manifest owns everything under the port root: never guess it is empty."""
    root = Path(project_root)
    manifest = root / PORT_MANIFEST
    if not manifest.is_file():
        return frozenset()
    try:
        files = json.loads(manifest.read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError, AttributeError):
        return frozenset(
            p.relative_to(root).as_posix()
            for p in (root / PORT_ROOT).rglob("*")
            if p.is_file()
        )
    return frozenset(f"{PORT_ROOT}/{path}" for path in files)


def editable_frontend_files(project_root: Path) -> list[str]:
    """The frontend source files the daily work may touch, project-relative."""
    root = Path(project_root).resolve()
    owned = port_managed(root)
    return [
        rel
        for rel in (p.relative_to(root).as_posix() for p in frontend_files(root))
        if rel not in owned
    ]


__all__ = [
    "LintMessage",
    "PORT_MANIFEST",
    "StaticCheckUnavailable",
    "StaticResult",
    "check_texts",
    "editable_frontend_files",
    "port_managed",
]
