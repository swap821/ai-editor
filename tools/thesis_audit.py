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
    "aios/core/router_wiring.py",
    "tests/adversarial/test_cloud_privacy.py",
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


def audit_repo(root: Path) -> list[Finding]:
    """Audit the current repository for load-bearing thesis/config drift."""
    docs: dict[str, str] = {}
    for rel in DEFAULT_DOCS:
        path = root / rel
        try:
            docs[rel] = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            docs[rel] = ""
    return audit_cloud_routing_docs(
        docs,
        cloud_tasks_default=config._ROUTER_CLOUD_TASKS_DEFAULT,
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
