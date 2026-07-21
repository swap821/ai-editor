"""Tests for the self-curriculum miner."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite DB with the expected schema."""
    from aios.memory.db import init_memory_db
    db_path = tmp_path / "memory.db"
    init_memory_db(db_path)
    return db_path


@pytest.fixture
def seed_db(tmp_db):
    """Seed the DB with some verified-success development events."""
    from aios.memory.db import get_connection
    with get_connection(tmp_db) as conn:
        for i in range(5):
            task_text = (
                f"Create training_ground/module_{i}.py with a function process_{i}(data) that transforms data. "
                f"Then create training_ground/test_module_{i}.py with pytest tests. Then verify that the tests pass."
            )
            conn.execute(
                "INSERT INTO development_events (task_text, task_signature, outcome) VALUES (?, ?, ?)",
                (task_text, f"sig-{i}", "verified_success"),
            )
    return tmp_db


class TestCurriculumProposal:
    def test_fingerprint_deterministic(self):
        from aios.memory.curriculum_miner import CurriculumProposal
        p = CurriculumProposal(
            skill_name="python-general",
            level=3,
            prompt="Create training_ground/x.py with a thing",
            rationale="test",
            source_pattern="source",
            difficulty_delta="level 3",
        )
        assert len(p.fingerprint) == 16
        assert p.fingerprint == p.fingerprint

    def test_different_prompts_different_fingerprints(self):
        from aios.memory.curriculum_miner import CurriculumProposal
        p1 = CurriculumProposal("s", 1, "prompt A", "r", "sp", "d")
        p2 = CurriculumProposal("s", 1, "prompt B", "r", "sp", "d")
        assert p1.fingerprint != p2.fingerprint


class TestHelpers:
    def test_infer_skill_data_structures(self):
        from aios.memory.curriculum_miner import _infer_skill
        assert _infer_skill("implement a stack with push and pop") == "python-data-structures"

    def test_infer_skill_algorithms(self):
        from aios.memory.curriculum_miner import _infer_skill
        assert _infer_skill("implement quicksort algorithm") == "python-algorithms"

    def test_infer_skill_string_processing(self):
        from aios.memory.curriculum_miner import _infer_skill
        assert _infer_skill("parse a CSV file") == "python-string-processing"

    def test_infer_skill_general_fallback(self):
        from aios.memory.curriculum_miner import _infer_skill
        assert _infer_skill("do something completely generic") == "python-general"

    def test_extract_module_name(self):
        from aios.memory.curriculum_miner import _extract_module_name
        assert _extract_module_name("Create training_ground/my_mod.py with stuff") == "my_mod"
        assert _extract_module_name("no module here") is None

    def test_task_complexity_score(self):
        from aios.memory.curriculum_miner import _task_complexity_score
        assert _task_complexity_score("simple task") == 0
        assert _task_complexity_score("handle edge case and error") >= 2
        assert _task_complexity_score("Edit and refactor with parametrize") >= 2


class TestMineFromDevelopment:
    def test_empty_db_returns_empty(self, tmp_db):
        from aios.memory.curriculum_miner import CurriculumMiner
        miner = CurriculumMiner(db_path=tmp_db)
        proposals = miner.mine_from_development(existing_prompts=set())
        assert proposals == []

    def test_seeded_db_returns_proposals(self, seed_db):
        from aios.memory.curriculum_miner import CurriculumMiner
        miner = CurriculumMiner(db_path=seed_db)
        proposals = miner.mine_from_development(existing_prompts=set(), max_proposals=5)
        assert len(proposals) > 0
        for p in proposals:
            assert p.skill_name
            assert p.level >= 2
            assert "training_ground/" in p.prompt

    def test_respects_max_proposals(self, seed_db):
        from aios.memory.curriculum_miner import CurriculumMiner
        miner = CurriculumMiner(db_path=seed_db)
        proposals = miner.mine_from_development(existing_prompts=set(), max_proposals=2)
        assert len(proposals) <= 2

    def test_deduplicates_against_existing(self, seed_db):
        from aios.memory.curriculum_miner import CurriculumMiner
        miner = CurriculumMiner(db_path=seed_db)
        first_batch = miner.mine_from_development(existing_prompts=set(), max_proposals=5)
        existing = {p.prompt for p in first_batch}
        second_batch = miner.mine_from_development(existing_prompts=existing, max_proposals=5)
        for p in second_batch:
            assert p.prompt not in existing


class TestMineFromAuditLog:
    def test_missing_file_returns_empty(self, tmp_db, tmp_path):
        from aios.memory.curriculum_miner import CurriculumMiner
        miner = CurriculumMiner(db_path=tmp_db)
        proposals = miner.mine_from_audit_log(
            tmp_path / "nonexistent.jsonl", existing_prompts=set()
        )
        assert proposals == []

    def test_parses_session_complete_records(self, tmp_db, tmp_path):
        from aios.memory.curriculum_miner import CurriculumMiner
        log_file = tmp_path / "audit.jsonl"
        records = [
            {"kind": "session-complete", "outcome": "verified_success",
             "prompt": "Create training_ground/audit_mod.py with a function compute(x) that returns x*2. Then create training_ground/test_audit_mod.py with pytest tests. Then verify that the tests pass."},
            {"kind": "session-complete", "outcome": "verified_failure",
             "prompt": "Should be ignored"},
        ]
        log_file.write_text("\n".join(json.dumps(r) for r in records))

        miner = CurriculumMiner(db_path=tmp_db)
        proposals = miner.mine_from_audit_log(log_file, existing_prompts=set())
        assert len(proposals) >= 1
        assert all("training_ground/" in p.prompt for p in proposals)

    def test_parses_turn_done_records(self, tmp_db, tmp_path):
        from aios.memory.curriculum_miner import CurriculumMiner
        log_file = tmp_path / "audit.jsonl"
        records = [
            {"kind": "turn-done", "outcome": "verified_success",
             "prompt": "Create training_ground/turn_mod.py with a function hello() that returns 'world'. Then create training_ground/test_turn_mod.py with pytest tests. Then verify that the tests pass."},
        ]
        log_file.write_text("\n".join(json.dumps(r) for r in records))

        miner = CurriculumMiner(db_path=tmp_db)
        proposals = miner.mine_from_audit_log(log_file, existing_prompts=set())
        assert len(proposals) >= 1

    def test_handles_malformed_json(self, tmp_db, tmp_path):
        from aios.memory.curriculum_miner import CurriculumMiner
        log_file = tmp_path / "audit.jsonl"
        log_file.write_text("not json\n{bad\n")

        miner = CurriculumMiner(db_path=tmp_db)
        proposals = miner.mine_from_audit_log(log_file, existing_prompts=set())
        assert proposals == []


class TestListProposals:
    def test_combines_sources(self, seed_db, tmp_path):
        from aios.memory.curriculum_miner import CurriculumMiner
        import aios.config as cfg

        audit_dir = tmp_path / ".aios" / "audit"
        audit_dir.mkdir(parents=True)
        log_file = audit_dir / "test.jsonl"
        log_file.write_text(json.dumps({
            "kind": "session-complete",
            "outcome": "verified_success",
            "prompt": "Create training_ground/combined_mod.py with a function add(a, b). Then create training_ground/test_combined_mod.py with pytest tests. Then verify that the tests pass.",
        }))

        with patch.object(cfg, "PROJECT_ROOT", str(tmp_path)):
            miner = CurriculumMiner(db_path=seed_db)
            proposals = miner.list_proposals(max_proposals=10)
            assert len(proposals) >= 1
