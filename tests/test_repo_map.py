from __future__ import annotations

import json
from pathlib import Path

from aios.cognition.repo_map import (
    query_symbols,
    scan_symbol_repo_map,
    scope_hints_for_contract,
)
from aios.memory.project_passport import harvest_project_passport
from aios.runtime.contracts import MissionContract


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _contract(root: Path, *, goal: str, allowed_files: list[str]) -> MissionContract:
    return MissionContract(
        mission_id="mission-repomap",
        goal=goal,
        worker_type="builder",
        created_by="test",
        workspace_root=str(root),
        allowed_files=allowed_files,
        allowed_tools=["read_file", "write_file"],
        verification_commands=["python -m pytest"],
    )


def test_symbol_repo_map_is_local_proposal_evidence_over_project_passport(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "README.md", "# Demo Service\n\nA FastAPI service.\n")
    _write(tmp_path / "pyproject.toml", "[project]\ndependencies=['fastapi']\n")
    _write(
        tmp_path / "pkg" / "service.py",
        "import pkg.util\n\nclass Service:\n    def run(self):\n        return helper()\n\n"
        "def helper():\n    return 'ok'\n",
    )
    _write(tmp_path / "pkg" / "util.py", "def normalize(value):\n    return value\n")

    repo_map = scan_symbol_repo_map(tmp_path)

    assert repo_map.activation == "proposal/evidence"
    assert repo_map.trusted_memory_activated is False
    assert repo_map.local_only is True
    assert repo_map.cloud_calls == 0
    assert repo_map.project_passport["activation"] == "proposal/evidence"
    assert repo_map.project_passport["trustedMemoryActivated"] is False
    assert repo_map.project_passport["purpose"].startswith("Demo Service")
    assert "pkg/service.py" in repo_map.evidence_files
    symbol_ids = {symbol.symbol_id for symbol in repo_map.symbols}
    assert "pkg.service:Service" in symbol_ids
    assert "pkg.service:helper" in symbol_ids
    assert any(edge.source == "pkg.service" and edge.target == "pkg.util" for edge in repo_map.edges)


def test_symbol_repo_map_skips_secret_paths_and_values(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "# Secret Demo\n")
    _write(tmp_path / ".env", "API_KEY=super-secret-value\n")
    _write(tmp_path / "id_ed25519", "private-key-material\n")
    _write(tmp_path / "pkg" / "app.py", "def public_entrypoint():\n    return 'safe'\n")

    repo_map = scan_symbol_repo_map(tmp_path)
    payload = json.dumps(repo_map.as_dict())

    assert ".env" not in repo_map.evidence_files
    assert "id_ed25519" not in repo_map.evidence_files
    assert "super-secret-value" not in payload
    assert "private-key-material" not in payload
    assert {symbol.file for symbol in repo_map.symbols} == {"pkg/app.py"}


def test_symbol_query_ranking_is_deterministic(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "# Rank Demo\n")
    _write(tmp_path / "pkg" / "alpha.py", "import pkg.beta\n\ndef handle_alpha():\n    pass\n")
    _write(tmp_path / "pkg" / "beta.py", "def handle_beta():\n    pass\n")

    first = scan_symbol_repo_map(tmp_path)
    second = scan_symbol_repo_map(tmp_path)

    first_ids = [symbol.symbol_id for symbol in query_symbols(first, "handle")]
    second_ids = [symbol.symbol_id for symbol in query_symbols(second, "handle")]
    assert first_ids == second_ids
    assert first_ids == ["pkg.alpha:handle_alpha", "pkg.beta:handle_beta"]


def test_scope_hints_cannot_widen_worker_contract_scope(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "# Scope Demo\n")
    _write(tmp_path / "pkg" / "billing.py", "def charge_card():\n    return 'charged'\n")
    _write(tmp_path / "pkg" / "other.py", "def unrelated():\n    return None\n")
    repo_map = scan_symbol_repo_map(tmp_path)

    blocked = scope_hints_for_contract(
        repo_map,
        _contract(
            tmp_path,
            goal="Update charge_card behavior",
            allowed_files=["pkg/other.py"],
        ),
    )
    allowed = scope_hints_for_contract(
        repo_map,
        _contract(
            tmp_path,
            goal="Update charge_card behavior",
            allowed_files=["pkg/billing.py", "pkg/other.py"],
        ),
    )

    assert blocked.authority == "proposal/evidence"
    assert blocked.can_widen_scope is False
    assert blocked.recommended_files == []
    assert blocked.out_of_scope_matches == ["pkg/billing.py"]
    assert allowed.recommended_files == ["pkg/billing.py"]
    assert allowed.out_of_scope_matches == []


def test_project_passport_memory_safety_still_holds_with_repo_map(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "# Passport Safety\n")
    _write(tmp_path / "pkg" / "app.py", "def entrypoint():\n    return True\n")

    passport = harvest_project_passport(tmp_path)
    repo_map = scan_symbol_repo_map(tmp_path)

    assert passport.activation == "proposal/evidence"
    assert passport.trusted_memory_activated is False
    assert repo_map.project_passport["activation"] == "proposal/evidence"
    assert repo_map.trusted_memory_activated is False
