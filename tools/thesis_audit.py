"""Machine checks for load-bearing thesis/config claims.

This script intentionally starts narrow. It guards claims that are easy to let
rot and expensive to misunderstand: cloud routing defaults and documented
egress controls. It is local-only and reads repository files plus `aios.config`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys
from collections.abc import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aios import config


DEFAULT_DOCS: tuple[str, ...] = (
    "README.md",
    "AGENTS.md",
    ".aios/state/PLAN.md",
    ".aios/state/SYSTEM_TRUE_PICTURE.md",
    "aios/core/router_wiring.py",
    "tests/adversarial/test_cloud_privacy.py",
)

POST_V7_DOCS: tuple[str, ...] = (
    "README.md",
    ".aios/state/AUDIT.md",
    ".aios/state/GAGOS_ULTRA_PLAN.md",
    ".aios/state/V10_INTEGRATION_AUDIT.md",
    ".aios/state/V10_INTEGRATION_PLAN.md",
)

CANONICAL_CLOUD_DOCS: frozenset[str] = frozenset(
    {"README.md", "AGENTS.md", ".aios/state/PLAN.md"}
)

SWARM_EGRESS_DOCS: frozenset[str] = frozenset({"README.md", "AGENTS.md"})

STALE_LOCAL_ONLY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"empty\s+by\s+default\s*=\s*local-only", re.IGNORECASE),
    re.compile(r"local-only\s+by\s+default", re.IGNORECASE),
    re.compile(r"default\s+local-only", re.IGNORECASE),
    re.compile(r"cloud\s+is\s+opt-in,\s+not\s+default", re.IGNORECASE),
    re.compile(r"cloud\s+route\s+requires\s+per-task-class\s+operator\s+opt-in", re.IGNORECASE),
    re.compile(r"default\s+empty\s+`?ROUTER_CLOUD_TASKS`?", re.IGNORECASE),
)


@dataclass(frozen=True)
class Finding:
    path: str
    code: str
    message: str


@dataclass(frozen=True)
class FeatureDocRule:
    code: str
    name: str
    evidence_paths: tuple[str, ...]
    stale_patterns: tuple[re.Pattern[str], ...]


POST_V7_FEATURE_RULES: tuple[FeatureDocRule, ...] = (
    FeatureDocRule(
        code="post-v7-project-passport-drift",
        name="Project Passport / Project Knowledge",
        evidence_paths=(
            "aios/memory/project_passport.py",
            "tests/test_project_passport.py",
        ),
        stale_patterns=(
            re.compile(r"Project Knowledge\s*\|[^\n]*designed[^\n]*Project Passport[^\n]*roadmap", re.IGNORECASE),
            re.compile(r"P3\s*[-\u2013\u2014]\s*Project Knowledge\s*\(Roadmap\)", re.IGNORECASE),
            re.compile(r"\*{0,2}DESIGNED,\s*not built:\*{0,2}\s*Project Passport", re.IGNORECASE),
            re.compile(r"Project Passport harvester\s*\(P3,\s*XL,\s*local-only enforced\)", re.IGNORECASE),
        ),
    ),
    FeatureDocRule(
        code="post-v7-pheromone-contract-drift",
        name="Pheromone contract wiring",
        evidence_paths=(
            "aios/memory/pheromones.py",
            "tests/test_pheromones.py",
        ),
        stale_patterns=(
            re.compile(
                r"wire or remove the orphaned\s+`?PheromoneStore\.for_contract`?\s+hook",
                re.IGNORECASE,
            ),
        ),
    ),
    FeatureDocRule(
        code="post-v10-ecosystem-scanner-drift",
        name="Ecosystem Scanner",
        evidence_paths=(
            "aios/maintenance/ecosystem_scanner.py",
            "tests/test_ecosystem_scanner.py",
        ),
        stale_patterns=(
            re.compile(r"Ecosystem Scanner\s*\|[^\n]*Roadmap", re.IGNORECASE),
            re.compile(
                r"Phase 3\s*[-\u2013\u2014]\s*Ecosystem Scanner\s*\|[^\n]*Recommended next",
                re.IGNORECASE,
            ),
            re.compile(r"Start Phase 3 only", re.IGNORECASE),
            re.compile(
                r"Next safe implementation scope is\s+Phase 3",
                re.IGNORECASE,
            ),
            re.compile(
                r"Status:\s*Phase 0,\s*Phase 1,\s*and Phase 2 implemented",
                re.IGNORECASE,
            ),
        ),
    ),
    FeatureDocRule(
        code="post-v10-meta-loop-drift",
        name="Meta-Loop and Council Self-Assessment",
        evidence_paths=(
            "aios/learning/meta_loop.py",
            "tests/test_meta_loop.py",
        ),
        stale_patterns=(
            re.compile(r"Phase 6\s*[-\u2013\u2014]\s*Meta Loop\s*\|[^\n]*Planned", re.IGNORECASE),
            re.compile(r"Phase 6\s*[-\u2013\u2014]\s*Runtime Wiring And UI Truth", re.IGNORECASE),
            re.compile(r"Phase 6\s*[-\u2013\u2014][^\n]*UI Truth", re.IGNORECASE),
        ),
    ),
)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _cloud_tasks_literal(cloud_tasks_default: Sequence[str]) -> str:
    return ",".join(cloud_tasks_default)


def _has_local_only_override(text: str) -> bool:
    compact = _compact(text)
    return (
        'AIOS_ROUTER_CLOUD_TASKS=""' in compact
        or "AIOS_ROUTER_CLOUD_TASKS=''" in compact
        or "emptystring" in compact.lower()
        or "blank" in text.lower() and "AIOS_ROUTER_CLOUD_TASKS" in text
    )


def audit_cloud_routing_docs(
    docs: Mapping[str, str],
    *,
    cloud_tasks_default: Sequence[str],
) -> list[Finding]:
    """Return findings for stale cloud-routing claims in *docs*."""
    expected = _cloud_tasks_literal(cloud_tasks_default)
    findings: list[Finding] = []
    for path, text in docs.items():
        for pattern in STALE_LOCAL_ONLY_PATTERNS:
            if pattern.search(text):
                findings.append(
                    Finding(
                        path=path,
                        code="router-cloud-default-drift",
                        message=(
                            "stale local-only/default opt-in wording conflicts "
                            f"with config default {expected!r}"
                        ),
                    )
                )
                break

        if path in CANONICAL_CLOUD_DOCS:
            if expected not in _compact(text):
                findings.append(
                    Finding(
                        path=path,
                        code="router-cloud-default-missing",
                        message=f"document must name current cloud-task default {expected!r}",
                    )
                )
            if not _has_local_only_override(text):
                findings.append(
                    Finding(
                        path=path,
                        code="router-cloud-local-override-missing",
                        message='document must explain AIOS_ROUTER_CLOUD_TASKS="" local-only override',
                    )
                )

        if path in SWARM_EGRESS_DOCS and "AIOS_SWARM_CLOUD_BURST" not in text:
            findings.append(
                Finding(
                    path=path,
                    code="swarm-cloud-burst-undocumented",
                    message="document must disclose AIOS_SWARM_CLOUD_BURST as a separate egress control",
                )
            )
    return findings


def _evidence_paths_are_real(root: Path, evidence_paths: tuple[str, ...]) -> bool:
    """True when every evidence path exists AND, for .py files, is actually
    importable -- catches a stub/broken file passing the weaker "exists"
    check while genuinely being unfinished (the class of gap that let
    aios/learning/meta_loop.py's own drift rule apply before the module had
    any real caller: file-existence alone can't distinguish "wired in" from
    "sits on disk unused" -- but a module that doesn't even import cleanly
    is unambiguously not a real implementation, regardless of caller count).
    """
    for rel in evidence_paths:
        path = root / rel
        if not path.exists():
            return False
        if path.suffix != ".py":
            continue
        module_name = rel[: -len(".py")].replace("/", ".").replace("\\", ".")
        try:
            import importlib

            importlib.import_module(module_name)
        except Exception:
            return False
    return True


def audit_post_v7_feature_docs(
    docs: Mapping[str, str],
    *,
    root: Path,
    rules: Sequence[FeatureDocRule] = POST_V7_FEATURE_RULES,
) -> list[Finding]:
    """Return findings when docs say a post-v7 built feature is still missing."""
    findings: list[Finding] = []
    for rule in rules:
        if not _evidence_paths_are_real(root, rule.evidence_paths):
            continue
        for path, text in docs.items():
            for pattern in rule.stale_patterns:
                if pattern.search(text):
                    findings.append(
                        Finding(
                            path=path,
                            code=rule.code,
                            message=(
                                f"stale docs describe {rule.name} as missing "
                                "even though code/test evidence exists"
                            ),
                        )
                    )
                    break
    return findings


def audit_repo(root: Path) -> list[Finding]:
    """Audit the current repository for load-bearing thesis/config drift."""
    docs: dict[str, str] = {}
    for rel in tuple(dict.fromkeys((*DEFAULT_DOCS, *POST_V7_DOCS))):
        path = root / rel
        try:
            docs[rel] = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            docs[rel] = ""
    return (
        audit_cloud_routing_docs(
            docs,
            cloud_tasks_default=config._ROUTER_CLOUD_TASKS_DEFAULT,
        )
        + audit_post_v7_feature_docs(docs, root=root)
    )


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(argv[0]) if argv else Path.cwd()
    findings = audit_repo(root.resolve())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.code}: {finding.message}")
        return 1
    print("thesis audit: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
