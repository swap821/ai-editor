from __future__ import annotations

from pathlib import Path

import re

from tools.thesis_audit import (
    FeatureDocRule,
    Finding,
    audit_cloud_routing_docs,
    audit_post_v7_feature_docs,
    audit_repo,
)


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


def test_post_v7_audit_catches_features_documented_as_missing(tmp_path: Path) -> None:
    (tmp_path / "aios/memory").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "aios/memory/project_passport.py").write_text("", encoding="utf-8")
    (tmp_path / "tests/test_project_passport.py").write_text("", encoding="utf-8")

    findings = audit_post_v7_feature_docs(
        {
            "README.md": (
                "| Project Knowledge | designed | scans repos into a "
                "Project Passport (roadmap) |"
            )
        },
        root=tmp_path,
        rules=(
            FeatureDocRule(
                code="project-passport-stale",
                name="Project Passport",
                evidence_paths=(
                    "aios/memory/project_passport.py",
                    "tests/test_project_passport.py",
                ),
                stale_patterns=(re.compile(r"Project Passport.*roadmap", re.IGNORECASE),),
            ),
        ),
    )

    assert findings == [
        Finding(
            path="README.md",
            code="project-passport-stale",
            message=(
                "stale docs describe Project Passport as missing "
                "even though code/test evidence exists"
            ),
        )
    ]


def test_post_v10_audit_catches_ecosystem_documented_as_roadmap(
    tmp_path: Path,
) -> None:
    (tmp_path / "aios/maintenance").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "aios/maintenance/ecosystem_scanner.py").write_text(
        "",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_ecosystem_scanner.py").write_text("", encoding="utf-8")

    findings = audit_post_v7_feature_docs(
        {
            "README.md": (
                "| Ecosystem Scanner | Roadmap | Phase 3 target: local-only scanner |"
            ),
            ".aios/state/V10_INTEGRATION_PLAN.md": "Start Phase 3 only",
        },
        root=tmp_path,
    )

    assert {finding.path for finding in findings} == {
        "README.md",
        ".aios/state/V10_INTEGRATION_PLAN.md",
    }
    assert all(finding.code == "post-v10-ecosystem-scanner-drift" for finding in findings)
