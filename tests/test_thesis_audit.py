from __future__ import annotations

from pathlib import Path

from tools.thesis_audit import Finding, audit_cloud_routing_docs, audit_repo


ROOT = Path(__file__).resolve().parents[1]


def _format(findings: list[Finding]) -> str:
    return "\n".join(f"{f.path}: {f.code}: {f.message}" for f in findings)


def test_canonical_thesis_docs_match_cloud_routing_config() -> None:
    findings = audit_repo(ROOT)
    assert findings == [], _format(findings)


def test_cloud_routing_audit_catches_stale_local_only_default_claim() -> None:
    findings = audit_cloud_routing_docs(
        {
            "README.md": (
                "AIOS_ROUTER_CLOUD_TASKS controls cloud egress; "
                "empty by default = local-only."
            )
        },
        cloud_tasks_default=("reasoning", "coding"),
    )

    assert any(f.code == "router-cloud-default-drift" for f in findings)
