from __future__ import annotations

import ast
from pathlib import Path


_LEGACY_TYPES = frozenset(
    {
        "EpisodicMemory",
        "SemanticMemory",
        "SemanticFacts",
        "SkillMemory",
        "MistakeMemory",
        "PheromoneStore",
        "WorkingMemory",
        "CouncilMemory",
        "DevelopmentTracker",
    }
)

# Existing specialists still own physical stores in these compatibility seams.
# The explicit manifest makes that debt visible and fails CI when a new
# production bypass is introduced. R11 removes entries as each seam migrates
# behind MemoryAuthority adapters.
_KNOWN_COMPATIBILITY_SEAMS = {
    "aios/api/deps.py",
    "aios/api/routes/council.py",
    "aios/application/memory/adapters.py",
}


def test_legacy_memory_construction_is_explicitly_quarantined() -> None:
    root = Path(__file__).resolve().parents[1]
    violations = {
        path.relative_to(root).as_posix()
        for path in (root / "aios").rglob("*.py")
        if any(
            isinstance(node.func, ast.Name) and node.func.id in _LEGACY_TYPES
            for node in ast.walk(
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            )
            if isinstance(node, ast.Call)
        )
    }
    assert violations == _KNOWN_COMPATIBILITY_SEAMS


def test_main_memory_facades_are_authority_owned_adapters() -> None:
    from aios.api.deps import get_memory_authority
    from aios.api.main import _EPISODIC, _SEMANTIC, _WORKING

    authority = get_memory_authority()

    assert _EPISODIC is authority.adapters["episodic"]
    assert _SEMANTIC is authority.adapters["semantic"]
    assert _WORKING is authority.adapters["working"]


def test_consolidator_dependency_returns_authority_owned_service() -> None:
    from aios.api.deps import get_memory_authority, get_memory_consolidator

    authority = get_memory_authority()
    consolidator = get_memory_consolidator()

    assert consolidator is authority.adapters["consolidation"].service
    assert authority.owns_store("consolidation", consolidator)


def test_authority_consolidator_reuses_registered_specialist_stores() -> None:
    from aios.api.deps import get_memory_authority

    authority = get_memory_authority()
    service = authority.adapters["consolidation"].service

    assert service.semantic is authority.adapters["semantic"].store
    assert service.mistakes is authority.adapters["lessons"].store
    assert service.facts is authority.adapters["facts"].store


def test_authority_bound_planner_and_reflection_reuse_registered_lesson_store() -> None:
    from aios.agents.reflection_agent import ReflectionAgent
    from aios.api.deps import get_memory_authority
    from aios.core.planner import Planner

    authority = get_memory_authority()
    lessons = authority.adapters["lessons"].store

    planner = Planner(object(), memory_authority=authority)
    reflection = ReflectionAgent(object(), memory_authority=authority)

    assert planner.mistakes is lessons
    assert planner.development is authority.adapters["development"].store
    assert planner.skills is authority.adapters["skills"].store
    assert reflection.mistakes is lessons


def test_semantic_indexer_dependency_returns_authority_adapter(monkeypatch) -> None:
    from aios import config
    from aios.api.deps import get_memory_authority, get_semantic_indexer

    monkeypatch.setattr(config, "INDEX_CHAT", True)
    authority = get_memory_authority()

    assert get_semantic_indexer() is authority.adapters["semantic"]


def test_development_read_routes_use_authority_when_store_owned() -> None:
    from aios.api.routes.development import (
        development_metrics,
        development_skills,
        development_trails,
    )

    class Authority:
        def owns_store(self, name, candidate):
            return name in {"development", "skills"}

        def development_summary(self):
            return {"source": "authority"}

        def skills_list(self, *, status=None):
            return [{"source": "authority", "status": status}]

        def skills_trail_map(self):
            return {"source": "authority"}

    class LegacyStore:
        def summary(self):
            raise AssertionError("development route bypassed MemoryAuthority")

        def list(self, *, status=None):
            raise AssertionError("skills route bypassed MemoryAuthority")

        def trail_map(self):
            raise AssertionError("trail route bypassed MemoryAuthority")

    authority = Authority()
    tracker = LegacyStore()
    skills = LegacyStore()

    assert development_metrics(tracker=tracker, authority=authority) == {
        "source": "authority"
    }
    assert development_skills(
        status="verified", skills=skills, authority=authority
    ) == {"skills": [{"source": "authority", "status": "verified"}]}
    assert development_trails(skills=skills, authority=authority) == {
        "source": "authority"
    }


def test_operator_model_route_uses_authority_when_facts_store_owned() -> None:
    from aios.api.routes.development import operator_model

    class Authority:
        def owns_store(self, name, candidate):
            return name == "facts"

        def operator_model(self):
            return {"source": "authority"}

    class LegacyFacts:
        def facts_for(self, *args, **kwargs):
            raise AssertionError("operator model bypassed MemoryAuthority")

    assert operator_model(facts=LegacyFacts(), authority=Authority()) == {
        "source": "authority"
    }


def test_system_metrics_route_uses_authority_when_tracker_store_owned(monkeypatch) -> None:
    from aios.api.routes import system

    class Authority:
        def owns_store(self, name, candidate):
            return name == "development"

        def development_summary(self):
            return {"verified_success_rate": 1.0, "average_tool_calls": 2.0}

    class LegacyTracker:
        def summary(self):
            raise AssertionError("system metrics bypassed MemoryAuthority")

    class Capabilities:
        def consumed_count(self):
            return 0

    class Autonomy:
        def earned_count(self):
            return 0

    monkeypatch.setattr(system._METRICS, "update", lambda *args, **kwargs: None)
    monkeypatch.setattr(system, "generate_latest", lambda registry: b"metrics")
    response = system.metrics(
        tracker=LegacyTracker(),
        capabilities=Capabilities(),
        autonomy=Autonomy(),
        authority=Authority(),
    )

    assert response.body == b"metrics"


def test_specialist_dependency_providers_return_authority_stores() -> None:
    from aios.api.deps import (
        get_development_tracker,
        get_memory_authority,
        get_mistake_memory,
        get_semantic_facts,
        get_skill_memory,
    )

    authority = get_memory_authority()
    facts = get_semantic_facts()

    assert facts is authority.adapters["facts"].store
    assert get_development_tracker(facts, authority) is authority.adapters["development"].store
    assert get_skill_memory(None, facts, authority) is authority.adapters["skills"].store
    assert get_mistake_memory(facts, authority) is authority.adapters["lessons"].store


def test_mirror_snapshot_helpers_use_authority_for_owned_stores() -> None:
    from aios.api.routes.mirror import _read_development_summary, _read_skill_trails

    class Authority:
        def owns_store(self, name, candidate):
            return name in {"development", "skills"}

        def development_summary(self):
            return {"source": "authority"}

        def skills_trail_map(self):
            return {"trails": [{"status": "verified"}], "source": "authority"}

    class LegacyStore:
        def summary(self):
            raise AssertionError("mirror summary bypassed MemoryAuthority")

        def trail_map(self):
            raise AssertionError("mirror trails bypassed MemoryAuthority")

    authority = Authority()
    assert _read_development_summary(LegacyStore(), authority) == {
        "source": "authority"
    }
    assert _read_skill_trails(LegacyStore(), authority) == {
        "trails": [{"status": "verified"}],
        "source": "authority",
    }


def test_generate_recall_preserves_explicit_noncanonical_fakes() -> None:
    from aios.api.turn_pipeline import _recall_facts, _recall_skills

    class Authority:
        @staticmethod
        def owns_store(_name, _candidate):
            return False

        def facts_search(self, _query):
            raise AssertionError("facts recall bypassed the explicit fake")

        def recall_skills(self, _query, _limit):
            raise AssertionError("skills recall bypassed the explicit fake")

    class Facts:
        def search(self, _query):
            return [{"subject": "project", "predicate": "uses", "object": "FastAPI"}]

        def neighbors(self, _node):
            return []

        def traverse_weighted(self, _node, **_kwargs):
            return []

    class Skills:
        def relevant_verified(self, _query, _limit):
            return [{"goal_pattern": "build api", "steps": ["test"]}]

    authority = Authority()
    facts = _recall_facts(Facts(), "api", authority=authority)
    skills = _recall_skills(Skills(), "api", authority=authority)

    assert facts is not None
    assert "project uses FastAPI" in facts.text
    assert skills == [{"goal_pattern": "build api", "steps": ["test"]}]


def test_reflection_recall_preserves_noncanonical_lesson_fake() -> None:
    from aios.agents.reflection_agent import ReflectionAgent
    from aios.api.turn_pipeline import _recall_lessons

    class Lessons:
        db_path = "explicit-fake"

        def pending_for_task(self, _task_id, _limit):
            return []

        def relevant_verified(self, _query, _limit):
            return [{"mistake_id": 7, "error_type": "Bug", "lesson_text": "verify"}]

    class Authority:
        @staticmethod
        def owns_store(_name, _candidate):
            return False

        def recall_lessons(self, _query, _task_id, _limit):
            raise AssertionError("lesson recall bypassed the explicit fake")

    reflector = ReflectionAgent(
        object(), mistakes=Lessons(), memory_authority=Authority()
    )

    assert _recall_lessons(reflector, "session", "query", authority=reflector.memory_authority) == [
        {"mistake_id": 7, "error_type": "Bug", "lesson_text": "verify"}
    ]
