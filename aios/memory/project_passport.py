"""Local-only Project Passport / RepoMap evidence harvester.

The scanner reads a repository tree and returns structured proposal/evidence.
It deliberately does not write semantic facts, episodic memory, or any trusted
store. Human review or an existing approval path must promote anything useful.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Optional

from aios.security.secret_scanner import scan_and_redact


_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
    "dist",
    "build",
    "coverage",
}
_SAFE_ENV_EXAMPLES = {".env.example", ".env.sample", ".env.template"}
_SECRET_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
_SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt", ".cer"}
_KEY_FILE_NAMES = {
    "README.md",
    "README.rst",
    "AGENTS.md",
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "Dockerfile",
    "docker-compose.yml",
    "Makefile",
    "vite.config.js",
    "vite.config.ts",
    "tsconfig.json",
}
_ENV_PATTERNS = (
    re.compile(r"\bos\.environ(?:\.get)?\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"\bgetenv\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"\bprocess\.env\.([A-Z][A-Z0-9_]{2,})\b"),
    re.compile(r"\b([A-Z][A-Z0-9_]{2,})\s*=", re.MULTILINE),
)
_ISSUE_RE = re.compile(r"\b(TODO|FIXME|BUG|HACK|XXX)\b[:\s-]*(.*)", re.IGNORECASE)


@dataclass(frozen=True)
class RepoScanLimits:
    max_files: int = 500
    max_depth: int = 5
    max_file_bytes: int = 64_000
    max_findings: int = 40


@dataclass(frozen=True)
class ProjectPassport:
    root: str
    generated_at: str
    purpose: str
    stack: list[str]
    folder_map: list[str]
    key_files: list[str]
    install_commands: list[str]
    run_commands: list[str]
    build_commands: list[str]
    test_commands: list[str]
    env_vars: list[str]
    safe_actions: list[str]
    risky_actions: list[str]
    known_issues: list[str]
    current_goals: list[str]
    suggested_improvements: list[str]
    evidence_files: list[str]
    activation: str = "proposal/evidence"
    trusted_memory_activated: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return API-ready data with explicit non-trusted-memory flags."""
        return {
            "root": self.root,
            "generatedAt": self.generated_at,
            "activation": self.activation,
            "trustedMemoryActivated": self.trusted_memory_activated,
            "purpose": self.purpose,
            "stack": self.stack,
            "folderMap": self.folder_map,
            "keyFiles": self.key_files,
            "installCommands": self.install_commands,
            "runCommands": self.run_commands,
            "buildCommands": self.build_commands,
            "testCommands": self.test_commands,
            "envVars": self.env_vars,
            "safeActions": self.safe_actions,
            "riskyActions": self.risky_actions,
            "knownIssues": self.known_issues,
            "currentGoals": self.current_goals,
            "suggestedImprovements": self.suggested_improvements,
            "evidenceFiles": self.evidence_files,
        }


def harvest_project_passport(
    root: Path | str,
    *,
    limits: Optional[RepoScanLimits] = None,
) -> ProjectPassport:
    """Scan *root* and return proposal/evidence, without activating memory."""
    resolved = Path(root).resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise FileNotFoundError(f"project root does not exist or is not a directory: {resolved}")
    scan_limits = limits or RepoScanLimits()
    files = list(_iter_scan_files(resolved, scan_limits))
    texts = _read_evidence_texts(resolved, files, scan_limits)

    key_files = _key_files(resolved, files)
    package_json = _load_package_json(texts.get("package.json"))
    pyproject = texts.get("pyproject.toml", "")

    return ProjectPassport(
        root=str(resolved),
        generated_at=datetime.now(timezone.utc).isoformat(),
        purpose=_purpose(texts),
        stack=_stack(files, texts, package_json, pyproject),
        folder_map=_folder_map(resolved, scan_limits),
        key_files=key_files,
        install_commands=_install_commands(files),
        run_commands=_script_commands(package_json, {"dev", "start", "serve"}),
        build_commands=_script_commands(package_json, {"build"}),
        test_commands=_test_commands(files, package_json, pyproject),
        env_vars=_env_vars(texts),
        safe_actions=_safe_actions(files),
        risky_actions=_risky_actions(resolved, files, texts),
        known_issues=_known_issues(texts, scan_limits),
        current_goals=_current_goals(texts),
        suggested_improvements=_suggested_improvements(files, package_json, pyproject),
        evidence_files=sorted(texts),
    )


def _iter_scan_files(root: Path, limits: RepoScanLimits) -> list[Path]:
    found: list[Path] = []
    for current, dirs, files in os.walk(root, topdown=True):
        current_path = Path(current)
        rel_dir = current_path.relative_to(root)
        depth = 0 if rel_dir == Path(".") else len(rel_dir.parts)
        if depth >= limits.max_depth:
            dirs[:] = []
        else:
            dirs[:] = [
                name
                for name in sorted(dirs)
                if name not in _IGNORED_DIRS and not _is_aios_private_dir(rel_dir / name)
            ]
        for name in sorted(files):
            path = current_path / name
            rel = path.relative_to(root)
            if _is_secret_path(rel) or _is_aios_private_dir(rel.parent):
                continue
            found.append(path)
            if len(found) >= limits.max_files:
                return found
    return found


def _is_aios_private_dir(rel: Path) -> bool:
    parts = rel.parts
    return len(parts) >= 2 and parts[0] == ".aios" and parts[1] in {"audit", "memory"}


def _is_secret_path(rel: Path) -> bool:
    name = rel.name
    lower = name.lower()
    if lower in _SAFE_ENV_EXAMPLES:
        return False
    return lower in _SECRET_FILENAMES or rel.suffix.lower() in _SECRET_SUFFIXES


def _read_evidence_texts(root: Path, files: list[Path], limits: RepoScanLimits) -> dict[str, str]:
    texts: dict[str, str] = {}
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw:
            continue
        if len(raw) > limits.max_file_bytes:
            raw = raw[: limits.max_file_bytes]
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            decoded = raw.decode("utf-8", errors="replace")
        texts[rel] = scan_and_redact(decoded).scrubbed
    return texts


def _key_files(root: Path, files: list[Path]) -> list[str]:
    keys: list[str] = []
    for path in files:
        if path.name in _KEY_FILE_NAMES or path.name in _SAFE_ENV_EXAMPLES:
            keys.append(path.relative_to(root).as_posix())
    return sorted(set(keys))


def _folder_map(root: Path, limits: RepoScanLimits) -> list[str]:
    entries: list[str] = []
    for current, dirs, files in os.walk(root, topdown=True):
        current_path = Path(current)
        rel_dir = current_path.relative_to(root)
        depth = 0 if rel_dir == Path(".") else len(rel_dir.parts)
        if depth > 2:
            dirs[:] = []
            continue
        dirs[:] = [
            name
            for name in sorted(dirs)
            if name not in _IGNORED_DIRS and not _is_aios_private_dir(rel_dir / name)
        ]
        if rel_dir != Path("."):
            entries.append(f"{rel_dir.as_posix()}/")
        for name in sorted(files):
            rel = (rel_dir / name) if rel_dir != Path(".") else Path(name)
            if _is_secret_path(rel) or _is_aios_private_dir(rel.parent):
                continue
            entries.append(rel.as_posix())
        if len(entries) >= limits.max_findings:
            return entries[: limits.max_findings]
    return entries[: limits.max_findings]


def _purpose(texts: dict[str, str]) -> str:
    for name in ("README.md", "README.rst"):
        text = texts.get(name)
        if not text:
            continue
        title = ""
        summary = ""
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#") and not title:
                title = stripped.lstrip("#").strip()
                continue
            if not stripped.startswith(("#", "!", "[", "<")):
                summary = stripped
                break
        if title and summary:
            return f"{title} - {summary[:180]}"
        if title:
            return title
    return "Unknown local project; no README summary found."


def _load_package_json(text: Optional[str]) -> dict[str, Any]:
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _stack(
    files: list[Path],
    texts: dict[str, str],
    package_json: dict[str, Any],
    pyproject: str,
) -> list[str]:
    names = {path.name for path in files}
    joined = "\n".join(texts.values()).lower()
    stack: set[str] = set()
    if {"pyproject.toml", "requirements.txt", "setup.py", "pytest.ini"} & names:
        stack.add("Python")
    if "fastapi" in pyproject.lower() or "fastapi" in joined:
        stack.add("FastAPI")
    if package_json:
        stack.add("Node")
        deps = {
            **_dict(package_json.get("dependencies")),
            **_dict(package_json.get("devDependencies")),
        }
        deps_text = " ".join(deps)
        scripts_text = " ".join(_dict(package_json.get("scripts")).values())
        if "react" in deps_text or "@vitejs/plugin-react" in deps_text:
            stack.add("React")
        if "vite" in deps_text or "vite" in scripts_text:
            stack.add("Vite")
    if {"Dockerfile", "docker-compose.yml", "compose.yml"} & names:
        stack.add("Docker")
    if "sqlite" in joined:
        stack.add("SQLite")
    return sorted(stack)


def _dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def _install_commands(files: list[Path]) -> list[str]:
    names = {path.name for path in files}
    commands: list[str] = []
    if "uv.lock" in names:
        commands.append("uv sync")
    if "requirements.txt" in names:
        commands.append("python -m pip install -r requirements.txt")
    if "pyproject.toml" in names:
        commands.append("python -m pip install -e .")
    if "package.json" in names:
        commands.append("npm ci" if "package-lock.json" in names else "npm install")
    return _dedupe(commands)


def _script_commands(package_json: dict[str, Any], script_names: set[str]) -> list[str]:
    scripts = _dict(package_json.get("scripts"))
    commands: list[str] = []
    for name in sorted(script_names):
        if name in scripts:
            commands.append(f"npm run {name}")
    return commands


def _test_commands(files: list[Path], package_json: dict[str, Any], pyproject: str) -> list[str]:
    names = {path.name for path in files}
    scripts = _dict(package_json.get("scripts"))
    commands: list[str] = []
    if "test" in scripts:
        commands.append("npm test")
    if (
        "pytest.ini" in names
        or "pyproject.toml" in names
        or "pytest" in pyproject.lower()
        or any("tests" in path.parts for path in files)
    ):
        commands.append("python -m pytest")
    return _dedupe(commands)


def _env_vars(texts: dict[str, str]) -> list[str]:
    envs: set[str] = set()
    for path, text in texts.items():
        if Path(path).name.startswith(".env") and Path(path).name not in _SAFE_ENV_EXAMPLES:
            continue
        for pattern in _ENV_PATTERNS:
            envs.update(match.group(1) for match in pattern.finditer(text))
    return sorted(envs)


def _safe_actions(files: list[Path]) -> list[str]:
    actions = ["read local repository files", "review Project Passport evidence"]
    if any("tests" in path.parts for path in files):
        actions.append("run listed test commands")
    return actions


def _risky_actions(root: Path, files: list[Path], texts: dict[str, str]) -> list[str]:
    risks = ["running install/build scripts may execute package hooks"]
    if any(path.relative_to(root).as_posix().startswith("aios/security/") for path in files):
        risks.append("editing frozen security core requires explicit Section VIII approval")
    if _env_vars(texts):
        risks.append("environment variable names are evidence only; never expose secret values")
    return risks


def _known_issues(texts: dict[str, str], limits: RepoScanLimits) -> list[str]:
    issues: list[str] = []
    for path, text in sorted(texts.items()):
        for idx, line in enumerate(text.splitlines(), start=1):
            match = _ISSUE_RE.search(line)
            if not match:
                continue
            issues.append(f"{path}:{idx}: {match.group(1).upper()} {match.group(2)[:160].strip()}")
            if len(issues) >= limits.max_findings:
                return issues
    return issues


def _current_goals(texts: dict[str, str]) -> list[str]:
    resume = texts.get(".aios/state/RESUME.md")
    if not resume:
        return []
    goals: list[str] = []
    capture = False
    for line in resume.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Current Goal") or stripped.startswith("## SINGLE NEXT ACTION"):
            capture = True
            continue
        if stripped.startswith("## ") and capture:
            capture = False
        elif capture and stripped:
            goals.append(stripped[:200])
        if len(goals) >= 4:
            break
    return goals


def _suggested_improvements(
    files: list[Path],
    package_json: dict[str, Any],
    pyproject: str,
) -> list[str]:
    suggestions = ["review this passport before promoting any item to trusted memory"]
    if not _test_commands(files, package_json, pyproject):
        suggestions.append("add a documented test command")
    if "README.md" not in {path.name for path in files}:
        suggestions.append("add a README with purpose and run instructions")
    return suggestions


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
