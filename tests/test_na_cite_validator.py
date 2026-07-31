"""Mechanical gate: every N/A-BY-DESIGN blocker cite must resolve."""

from __future__ import annotations

from pathlib import Path

from aios.application.governance.na_cite_validator import (
    _extract_cites_from_blocker,
    validate_na_cites,
    validate_shipped_na_cites,
)
from aios.application.governance.organ_ledger import load_ledger
from aios.domain.governance.contracts import OrganRecord

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"


def test_extract_cites_finds_python_and_frontend_paths() -> None:
    text = (
        "C4: N/A-BY-DESIGN — aios/security/gateway.py::RateLimiter and "
        "frontend/src/workbench/SovereignStatePanel.jsx::TruthfulMirrorAuthority"
    )
    cites = _extract_cites_from_blocker(text)
    assert ("aios/security/gateway.py", "RateLimiter") in cites
    assert (
        "frontend/src/workbench/SovereignStatePanel.jsx",
        "TruthfulMirrorAuthority",
    ) in cites


def test_validate_na_cites_rejects_missing_file(tmp_path: Path) -> None:
    record = OrganRecord(
        organ_id=1,
        name="Test",
        status="yellow",
        authority_owner="NobodyAuthority",
        known_blockers=(
            "C4: N/A-BY-DESIGN — aios/missing/module.py::MissingClass",
        ),
    )
    violations = validate_na_cites([record], repo_root=tmp_path)
    assert any("file does not exist" in v for v in violations)


def test_validate_na_cites_rejects_unresolvable_symbol(tmp_path: Path) -> None:
    module = tmp_path / "aios" / "probe.py"
    module.parent.mkdir(parents=True)
    module.write_text("class RealClass:\n    pass\n", encoding="utf-8")
    record = OrganRecord(
        organ_id=1,
        name="Test",
        status="yellow",
        authority_owner="NobodyAuthority",
        known_blockers=(
            "C4: N/A-BY-DESIGN — aios/probe.py::GhostClass",
        ),
    )
    violations = validate_na_cites([record], repo_root=tmp_path)
    assert any("GhostClass" in v for v in violations)


def test_validate_na_cites_accepts_class_method_and_wildcard(tmp_path: Path) -> None:
    module = tmp_path / "aios" / "edge.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "class EdgeTrustAuthority:\n"
        "    def check_api_token_or_loopback(self):\n"
        "        pass\n"
        "    def check_mutation_origin_or_token(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    record = OrganRecord(
        organ_id=6,
        name="Edge",
        status="yellow",
        authority_owner="EdgeTrustAuthority",
        known_blockers=(
            "C4: N/A-BY-DESIGN — aios/edge.py::EdgeTrustAuthority.check_*",
        ),
    )
    assert validate_na_cites([record], repo_root=tmp_path) == ()


def test_validate_na_cites_ignores_blockers_without_na_by_design(tmp_path: Path) -> None:
    record = OrganRecord(
        organ_id=1,
        name="Test",
        status="yellow",
        authority_owner="NobodyAuthority",
        known_blockers=("C3: PASS — aios/missing.py::Ghost",),
    )
    assert validate_na_cites([record], repo_root=tmp_path) == ()


def test_shipped_ledger_na_cites_have_zero_violations() -> None:
    violations = validate_shipped_na_cites(REPO_ROOT)
    assert violations == (), violations


def test_shipped_ledger_na_cite_count_is_nonzero() -> None:
    """Sanity: the gate is exercising real cites, not an empty ledger."""
    records = load_ledger(LEDGER_PATH)
    cite_count = sum(
        len(_extract_cites_from_blocker(blocker))
        for record in records
        for blocker in record.known_blockers
        if "N/A-BY-DESIGN" in blocker
    )
    assert cite_count >= 10
