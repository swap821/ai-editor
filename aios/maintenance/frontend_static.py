"""Static checks of frontend text with the project's own toolchain (2026-10-30).

GAGOS's daily frontend work (docs/learning/PAYOFF_PREREGISTRATION.md D14) judges a
proposed file BEFORE anyone has read it, so this module never executes the code
it judges. One node process, given ``{project-relative path: text}``, returns
for each text:

* ESLint's messages, from the project's own ``eslint.config.js`` through
  ``ESLint.lintText`` (the text is linted as if it were at its path, so the
  path's config and ignores apply, but nothing is written to disk);
* TypeScript's syntax diagnostics (``transpileModule``: parsing only, no types);
* on request (``inline_off``), ESLint's messages once more with inline
  configuration off (``allowInlineConfig: false``): every warning a disable
  comment or an inline config comment hides then shows, so a proposal's hidden
  warnings can be compared with the original's; and every comment, as ESLint's
  own parser sees it, so a directive is read only from a real comment, never
  from a string that looks like one (Codex's review of #574).

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
from collections import Counter
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
  // A rule that reports every comment the parser found: run with inline
  // configuration off, so no directive can switch it off.
  const comments = { meta: { type: 'suggestion', schema: [] }, create(context) {
    return { Program() { for (const c of context.sourceCode.getAllComments()) {
      context.report({ loc: c.loc, message: JSON.stringify({ kind: c.type, value: c.value,
        start: c.loc.start.line, end: c.loc.end.line }) });
    } } };
  } };
  const bare = input.inline_off ? new ESLint({ cwd: frontend, allowInlineConfig: false,
    overrideConfig: { plugins: { gagos: { rules: { comments } } },
      rules: { 'gagos/comments': 'warn' } } }) : null;
  const shape = (results) => (results[0] ? results[0].messages : []).map((m) => ({
    rule: m.ruleId || null, severity: m.severity, line: m.line || 0,
    column: m.column || 0, message: m.message, fatal: !!m.fatal,
  }));
  const out = {};
  for (const [rel, text] of Object.entries(input.files)) {
    const filePath = path.join(input.root, rel);
    const messages = shape(await eslint.lintText(text, { filePath }));
    const off = bare ? shape(await bare.lintText(text, { filePath })) : null;
    const inlineOff = off ? off.filter((m) => m.rule !== 'gagos/comments') : null;
    const found = off ? off.filter((m) => m.rule === 'gagos/comments').map((m) => JSON.parse(m.message)) : null;
    const parsed = ts.transpileModule(text, { fileName: filePath, reportDiagnostics: true,
      compilerOptions: { jsx: ts.JsxEmit.ReactJSX, allowJs: true } });
    const parse = (parsed.diagnostics || []).map((d) => ts.flattenDiagnosticMessageText(d.messageText, ' '));
    out[rel] = { messages, parse, inline_off: inlineOff, comments: found };
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
class Comment:
    """One comment as ESLint's parser saw it: ``Line`` or ``Block``, its text
    without the delimiters, and its first and last lines (1-based)."""

    kind: str
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class StaticResult:
    """What the toolchain says about one text. ``inline_off`` is ESLint's
    messages with inline configuration off and ``comments`` every comment in the
    text; each is None when that lint was not asked for."""

    messages: tuple[LintMessage, ...]
    parse_errors: tuple[str, ...] = field(default=())
    inline_off: tuple[LintMessage, ...] | None = None
    comments: tuple[Comment, ...] | None = None

    def warnings(self, rule: str | None = None) -> list[LintMessage]:
        return [
            m
            for m in self.messages
            if m.severity == 1 and (rule is None or m.rule == rule)
        ]

    @property
    def errors(self) -> list[LintMessage]:
        return [m for m in self.messages if m.severity == 2 or m.fatal]

    def hidden(self) -> list[LintMessage] | None:
        """What inline comments hide: the messages ESLint reports with inline
        configuration off and not with it on. None when that lint did not run."""
        if self.inline_off is None:
            return None
        shown = Counter(self.messages)
        out = []
        for m in self.inline_off:
            if shown[m]:
                shown[m] -= 1
            else:
                out.append(m)
        return out


def check_texts(
    project_root: Path,
    texts: Mapping[str, str],
    *,
    run: Callable[..., Any] = subprocess.run,
    timeout_s: float = 600,
    inline_off: bool = False,
) -> dict[str, StaticResult]:
    """Lint and parse each text as if it were at its project-relative path;
    with ``inline_off``, lint it a second time with inline configuration off."""
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
    payload = json.dumps(
        {"root": str(root), "files": dict(texts), "inline_off": bool(inline_off)}
    )
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
        off, found = entry.get("inline_off"), entry.get("comments")
        if inline_off and not (isinstance(off, list) and isinstance(found, list)):
            raise StaticCheckUnavailable(
                f"static checks returned no inline-off lint for {rel}"
            )
        results[rel] = StaticResult(
            messages=_messages(entry.get("messages", [])),
            parse_errors=tuple(str(e) for e in entry.get("parse", [])),
            inline_off=_messages(off) if inline_off else None,
            comments=(
                tuple(
                    Comment(
                        kind=str(c.get("kind", "")),
                        value=str(c.get("value", "")),
                        start=int(c.get("start", 0)),
                        end=int(c.get("end", 0)),
                    )
                    for c in found
                )
                if inline_off
                else None
            ),
        )
    return results


def _messages(raw: list) -> tuple[LintMessage, ...]:
    return tuple(
        LintMessage(
            rule=m.get("rule"),
            severity=int(m.get("severity", 0)),
            line=int(m.get("line", 0)),
            column=int(m.get("column", 0)),
            message=str(m.get("message", "")),
            fatal=bool(m.get("fatal", False)),
        )
        for m in raw
    )


def port_managed(project_root: Path) -> frozenset[str]:
    """Project-relative paths the lab-to-product port owns. A manifest that is
    missing, unreadable or not the expected shape owns everything under the
    port root: never guess it is empty (Codex's post-merge review of #566: a
    missing one made every port-owned file editable). An explicit empty
    ``files`` owns nothing."""
    root = Path(project_root)

    def everything() -> frozenset[str]:
        return frozenset(
            p.relative_to(root).as_posix()
            for p in (root / PORT_ROOT).rglob("*")
            if p.is_file()
        )

    try:
        files = json.loads((root / PORT_MANIFEST).read_text(encoding="utf-8"))["files"]
    except (OSError, ValueError, KeyError, TypeError):
        return everything()
    if not isinstance(files, dict) or not all(
        isinstance(path, str) and path for path in files
    ):
        return everything()
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
    "Comment",
    "LintMessage",
    "PORT_MANIFEST",
    "StaticCheckUnavailable",
    "StaticResult",
    "check_texts",
    "editable_frontend_files",
    "port_managed",
]
