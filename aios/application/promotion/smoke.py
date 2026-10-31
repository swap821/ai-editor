"""A promotion smoke check that checks: parse, import, and the tests that exercise it.

Promotion applies a staged repair to the enrolled project, then asks the smoke
check; a False answer makes PromotionAuthority restore the checkpoint. Until
2026-10-12 the production smoke (``deps.get_promotion_smoke_verifier``) passed
any target that existed and no longer held the two maintenance markers: nothing
was parsed, imported or tested, so a repair that broke the code would have been
promoted as verified.

For each Python target this now requires, in order, each step bounded by one
shared deadline:

1. the file compiles;
2. its module imports in a fresh interpreter (cwd = the project);
3. the project's tests that exercise it pass -- the test files that take any
   name from it, by the vulture's own cross-file index
   (aios/maintenance/dead_imports.py). With no such tests, steps 1-2 are the
   whole check, and the report says so.

The children get a private AIOS_DATA_DIR and PYTHONDONTWRITEBYTECODE, so the
check writes no databases or bytecode into the project it is judging. Every
step is recorded in a JSON report beside the operational data.

FRONTEND TARGETS (added 2026-10-30, GAGOS's daily frontend worker). Until then a
promotion whose targets were all ``.ts``/``.tsx``/``.js``/``.jsx`` passed with
"no Python targets": nothing was checked. Now each such target must, with the
project's own frontend toolchain (``frontend/node_modules``), in order:

1. parse (TypeScript, syntax only);
2. lint with no ESLint error (warnings are the codebase's own and recorded);
3. pass ``vitest related`` -- the tests that import it.

No toolchain in the project is a FAILED check, never a skipped one: the
maintenance project must have run ``npm ci`` in ``frontend/``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from aios.maintenance.dead_imports import ExternalImportIndex

_TAIL = 2_000


@dataclass
class SmokeStep:
    name: str
    passed: bool
    detail: str = ""
    seconds: float = 0.0
    command: list[str] = field(default_factory=list)


@dataclass
class SmokeReport:
    passed: bool
    reason: str
    targets: list[str]
    steps: list[SmokeStep]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=True)


def _module_name(project_root: Path, path: Path) -> str | None:
    parts = list(path.relative_to(project_root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts or not all(p.isidentifier() for p in parts):
        return None
    return ".".join(parts)


def _in_package(project_root: Path, path: Path) -> bool:
    """Every directory from the file up to the project root is a package."""
    directory = path.parent
    while directory != project_root:
        if not (directory / "__init__.py").is_file():
            return False
        directory = directory.parent
    return path.parent != project_root


def _is_test_file(project_root: Path, path: Path) -> bool:
    rel = path.relative_to(project_root)
    return rel.name.startswith("test_") and "tests" in rel.parts


def find_exercising_tests(project_root: Path, targets: Sequence[Path]) -> list[Path]:
    """Test files that import or name any target module, in any form (sorted).

    Not only the files that take a NAME from it: a test that imports the
    module and reaches into it dynamically takes no name a static index can
    see -- and that is precisely the use a static repair cannot judge.
    """
    index = ExternalImportIndex(project_root)
    found: set[Path] = set()
    for target in targets:
        found.update(
            s for s in index.files_importing(target) if _is_test_file(project_root, s)
        )
    return sorted(found - set(targets))


def python_smoke(
    project_root: Path,
    targets: Sequence[str],
    *,
    timeout_s: float,
    python: str = sys.executable,
    run: Callable[..., Any] = subprocess.run,
) -> SmokeReport:
    project_root = Path(project_root).resolve()
    deadline = time.monotonic() + timeout_s
    steps: list[SmokeStep] = []

    def fail(reason: str) -> SmokeReport:
        return SmokeReport(False, reason, list(targets), steps)

    paths: list[Path] = []
    frontend: list[Path] = []
    for target in targets:
        path = (project_root / target.replace("\\", "/")).resolve()
        try:
            path.relative_to(project_root)
        except ValueError:
            return fail(f"target escapes the project: {target}")
        if not path.is_file():
            return fail(f"target is missing after promotion: {target}")
        if path.suffix == ".py":
            paths.append(path)
        elif path.suffix in FRONTEND_SMOKE_SUFFIXES:
            frontend.append(path)
    if frontend:
        reason = frontend_smoke(
            project_root, frontend, deadline=deadline, run=run, steps=steps
        )
        if reason is not None:
            return fail(reason)
    if not paths:
        return SmokeReport(
            True,
            "frontend targets parse, lint without errors and pass their related tests"
            if frontend
            else "no Python targets",
            list(targets),
            steps,
        )

    for path in paths:
        started = time.monotonic()
        try:
            compile(path.read_bytes(), str(path), "exec")
        except SyntaxError as exc:
            steps.append(SmokeStep(f"compile {path.name}", False, str(exc)))
            return fail(f"{path.name} does not compile")
        steps.append(
            SmokeStep(f"compile {path.name}", True, seconds=time.monotonic() - started)
        )

    scratch = tempfile.mkdtemp(prefix="aios-smoke-")
    env = dict(os.environ, AIOS_DATA_DIR=scratch, PYTHONDONTWRITEBYTECODE="1")

    def child(name: str, argv: list[str]) -> bool:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            steps.append(SmokeStep(name, False, "deadline reached before the step"))
            return False
        started = time.monotonic()
        try:
            proc = run(
                argv,
                cwd=str(project_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=remaining,
            )
        except subprocess.TimeoutExpired:
            steps.append(
                SmokeStep(name, False, "timed out", time.monotonic() - started, argv)
            )
            return False
        ok = proc.returncode == 0
        tail = (proc.stdout or "")[-_TAIL:] + (proc.stderr or "")[-_TAIL:]
        steps.append(
            SmokeStep(
                name,
                ok,
                f"exit {proc.returncode}\n{tail}",
                time.monotonic() - started,
                argv,
            )
        )
        return ok

    for path in paths:
        module = _module_name(project_root, path)
        if module is None or not _in_package(project_root, path):
            # Importing runs top-level code: a library module's is what its
            # tests run anyway; a loose script's might DO something. Scripts
            # get compile + their tests, never an import.
            continue
        code = "import importlib, sys; importlib.import_module(sys.argv[1])"
        if not child(f"import {module}", [python, "-c", code, module]):
            return fail(f"{module} does not import")

    tests = find_exercising_tests(project_root, paths)
    if not tests:
        return SmokeReport(
            True,
            "compiles and imports; no test in the project exercises it",
            list(targets),
            steps,
        )
    argv = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if importlib.util.find_spec("pytest_cov") is not None:
        argv.append("--no-cov")
    argv += [str(t.relative_to(project_root)) for t in tests]
    if not child(f"pytest ({len(tests)} test files exercising the targets)", argv):
        return fail("the tests that exercise the targets did not pass")
    return SmokeReport(
        True,
        f"compiles, imports, and its {len(tests)} exercising test files pass",
        list(targets),
        steps,
    )


FRONTEND_SMOKE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs")
#: What the frontend smoke needs from ``frontend/node_modules``.
_FRONTEND_TOOLS = {
    "typescript": "typescript/package.json",
    "eslint": "eslint/bin/eslint.js",
    "vitest": "vitest/vitest.mjs",
}
#: Syntax only: TypeScript's transpile reports parse diagnostics, not types.
_PARSE_SCRIPT = (
    "const ts=require(process.argv[1]);const fs=require('fs');let bad=0;"
    "for(const f of process.argv.slice(2)){"
    "const out=ts.transpileModule(fs.readFileSync(f,'utf8'),{fileName:f,"
    "reportDiagnostics:true,compilerOptions:{jsx:ts.JsxEmit.ReactJSX,allowJs:true}});"
    "for(const d of out.diagnostics||[]){bad++;"
    "console.log(f+': '+ts.flattenDiagnosticMessageText(d.messageText,' '))}}"
    "process.exit(bad?1:0)"
)


def frontend_smoke(
    project_root: Path,
    targets: Sequence[Path],
    *,
    deadline: float,
    run: Callable[..., Any] = subprocess.run,
    steps: list[SmokeStep],
) -> str | None:
    """The frontend targets' smoke (module docstring): ``None`` when they pass,
    else the reason they do not. Each step is appended to *steps*."""
    frontend = project_root / "frontend"
    modules = frontend / "node_modules"
    node = shutil.which("node")
    missing = [
        name for name, rel in _FRONTEND_TOOLS.items() if not (modules / rel).is_file()
    ]
    if node is None or missing:
        detail = "node not found" if node is None else f"missing: {', '.join(missing)}"
        steps.append(SmokeStep("frontend toolchain", False, detail))
        return (
            "the frontend toolchain is unavailable in the project "
            f"({detail}); run `npm ci` in {frontend}"
        )
    steps.append(SmokeStep("frontend toolchain", True))
    rel = [t.relative_to(frontend).as_posix() for t in targets]

    def step(name: str, argv: list[str]) -> tuple[bool, str]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            steps.append(SmokeStep(name, False, "deadline reached before the step"))
            return False, ""
        started = time.monotonic()
        try:
            proc = run(
                argv,
                cwd=str(frontend),
                capture_output=True,
                text=True,
                timeout=remaining,
            )
        except subprocess.TimeoutExpired:
            steps.append(
                SmokeStep(name, False, "timed out", time.monotonic() - started, argv)
            )
            return False, ""
        out = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode == 0
        steps.append(
            SmokeStep(
                name,
                ok,
                f"exit {proc.returncode}\n{out[-_TAIL:]}",
                time.monotonic() - started,
                argv,
            )
        )
        return ok, proc.stdout or ""

    ok, _ = step(
        "parse (TypeScript)",
        [node, "-e", _PARSE_SCRIPT, str(modules / "typescript"), *rel],
    )
    if not ok:
        return "a frontend target does not parse"
    _ok, report = step(
        "eslint",
        [node, str(modules / _FRONTEND_TOOLS["eslint"]), "--format", "json", *rel],
    )
    try:
        errors = sum(
            1
            for result in json.loads(report or "[]")
            for message in result.get("messages", [])
            if message.get("severity") == 2 or message.get("fatal")
        )
    except ValueError:
        steps[-1].passed = False
        return "ESLint did not report a result"
    # ESLint exits non-zero on errors only; warnings are the codebase's own.
    steps[-1].passed = errors == 0
    if errors:
        return f"ESLint reports {errors} error(s) in the frontend targets"
    ok, _ = step(
        "vitest related",
        [
            node,
            str(modules / _FRONTEND_TOOLS["vitest"]),
            "related",
            *rel,
            "--run",
            "--passWithNoTests",
        ],
    )
    if not ok:
        return "the tests related to the frontend targets did not pass"
    return None


__all__ = [
    "FRONTEND_SMOKE_SUFFIXES",
    "SmokeReport",
    "SmokeStep",
    "find_exercising_tests",
    "frontend_smoke",
    "python_smoke",
]
