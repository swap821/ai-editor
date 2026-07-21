"""Tests for the boot attestation module."""

from __future__ import annotations

import json
from pathlib import Path

from aios.boot_attestation import attest_boot, compute_spine_hash, verify_spine_integrity


class TestComputeSpineHash:
    """Tests for compute_spine_hash."""

    def test_consistent_hash_for_same_content(self, tmp_path: Path) -> None:
        """Same file content produces the same hash on repeated calls."""
        (tmp_path / "a.py").write_text("print('hello')", encoding="utf-8")
        (tmp_path / "b.py").write_text("x = 1", encoding="utf-8")

        h1 = compute_spine_hash(tmp_path)
        h2 = compute_spine_hash(tmp_path)
        assert h1 == h2

    def test_hash_changes_when_file_changes(self, tmp_path: Path) -> None:
        """Modifying a file produces a different hash."""
        (tmp_path / "a.py").write_text("print('hello')", encoding="utf-8")
        (tmp_path / "b.py").write_text("x = 1", encoding="utf-8")

        h1 = compute_spine_hash(tmp_path)

        (tmp_path / "b.py").write_text("x = 2", encoding="utf-8")

        h2 = compute_spine_hash(tmp_path)
        assert h1 != h2

    def test_empty_directory_produces_deterministic_hash(self, tmp_path: Path) -> None:
        """An empty directory (no .py files) still returns a deterministic hash."""
        h1 = compute_spine_hash(tmp_path)
        h2 = compute_spine_hash(tmp_path)
        assert h1 == h2
        # Hash of empty string concatenation
        assert len(h1) == 64  # SHA-256 hex length


class TestVerifySpineIntegrity:
    """Tests for verify_spine_integrity."""

    def test_verify_returns_true_when_matching(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text("pass", encoding="utf-8")
        expected = compute_spine_hash(tmp_path)
        assert verify_spine_integrity(tmp_path, expected) is True

    def test_verify_returns_false_when_tampered(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text("pass", encoding="utf-8")
        assert verify_spine_integrity(tmp_path, "badhash") is False


class TestAttestBoot:
    """Tests for attest_boot."""

    def _setup_project(self, tmp_path: Path) -> Path:
        """Create a minimal project structure for testing."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        spine_dir = project_root / "aios" / "security"
        spine_dir.mkdir(parents=True)
        (spine_dir / "gateway.py").write_text("# gateway", encoding="utf-8")
        (spine_dir / "scope_lock.py").write_text("# scope_lock", encoding="utf-8")
        return project_root

    def test_first_boot_records_first_boot(self, tmp_path: Path) -> None:
        """First attestation with no prior log records 'first_boot'."""
        project_root = self._setup_project(tmp_path)

        result = attest_boot(project_root)

        assert result["integrity"] == "first_boot"
        assert result["previous_hash"] is None
        assert len(result["hash"]) == 64

        # Verify the JSONL file was created
        log_path = project_root / ".aios" / "audit" / "boot-attestation.jsonl"
        assert log_path.exists()
        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["integrity"] == "first_boot"
        assert entry["files_hashed"] == 2

    def test_subsequent_boot_valid(self, tmp_path: Path) -> None:
        """Second attestation with unchanged files records 'valid'."""
        project_root = self._setup_project(tmp_path)

        # First boot
        attest_boot(project_root)

        # Second boot
        result = attest_boot(project_root)

        assert result["integrity"] == "valid"
        assert result["previous_hash"] is not None
        assert result["hash"] == result["previous_hash"]

    def test_detects_tampering(self, tmp_path: Path) -> None:
        """Attestation detects when a spine file has been modified."""
        project_root = self._setup_project(tmp_path)

        # First boot records the hash
        first_result = attest_boot(project_root)

        # Simulate tampering
        spine_dir = project_root / "aios" / "security"
        (spine_dir / "gateway.py").write_text("# TAMPERED", encoding="utf-8")

        # Second boot should detect tampering
        result = attest_boot(project_root)

        assert result["integrity"] == "TAMPERED"
        assert result["previous_hash"] == first_result["hash"]
        assert result["hash"] != result["previous_hash"]

    def test_log_accumulates_entries(self, tmp_path: Path) -> None:
        """Each attestation appends a new line to the JSONL log."""
        project_root = self._setup_project(tmp_path)

        attest_boot(project_root)
        attest_boot(project_root)
        attest_boot(project_root)

        log_path = project_root / ".aios" / "audit" / "boot-attestation.jsonl"
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
