"""Authority-owned composition root for the canonical MemoryAuthority.

R11 (One Memory Authority) requires that legacy specialist stores are
constructed only behind :class:`~aios.application.memory.MemoryAuthority`.
This module is that single construction site: it builds the process-wide
authority, keeps the advisory pheromone adapter aligned with live
configuration, and composes mission-local Council memory scopes.

The API layer (``aios/api/deps.py``) delegates here and constructs no
physical store itself.  This file is the intentional, documented final
resting place of legacy-store construction (N/A-BY-DESIGN in the R11
quarantine manifest): a composition root must construct the stores it
owns, and doing so inside the authority's own package keeps the seam
visible, bounded, and CI-guarded.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from aios import config
from aios.application.memory.adapters import (
    AdvisoryPheromoneAdapter,
    CerebellumAdapter,
    CurriculumAdapter,
    DevelopmentHistoryAdapter,
    EpisodicMemoryAdapter,
    LegacySemanticMemoryAdapter,
    MemoryConsolidationAdapter,
    MistakeMemoryAdapter,
    SemanticFactsAdapter,
    WorkingMemoryAdapter,
)
from aios.application.memory.authority import MemoryAuthority
from aios.application.memory.institutional_skills import (
    SkillTrailIndex,
    build_skills_slot,
)
from aios.application.memory.provenance_policy import (
    ProvenanceWriter,
    RecallGate,
)
from aios.core.cerebellum import Cerebellum
from aios.domain.learning.repository import SkillRepository
from aios.infrastructure.memory import MemoryAuthorityStore
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.curriculum import CurriculumManager
from aios.memory.development import DevelopmentTracker
from aios.memory.episodic import EpisodicMemory
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.provenance import (
    LearningSigner,
    LearningVerifier,
    ProvenanceStore,
)
from aios.memory.semantic import SemanticMemory
from aios.memory.skills import SkillMemory
from aios.memory.working import WorkingMemory

if TYPE_CHECKING:
    from aios.council.council_memory import CouncilMemory
    from aios.council.council_state import CouncilState


def build_memory_authority() -> MemoryAuthority:
    """Construct the canonical process-wide MemoryAuthority.

    Every specialist store is created exactly once here and registered
    behind an authority adapter; the consolidator reuses the registered
    stores so no second physical store exists for the same data.
    """
    # One cerebellum for the process.
    #
    # `facts=` is deliberately NOT wired into the lesson store: its
    # graph-ingestion hook writes `semantic_facts` rows as ACTIVE with no
    # approver, laundering learned text into the channel recall presents as
    # "RELEVANT APPROVED FACTS" (threat T16, red-team RT-18).
    cerebellum = Cerebellum(config.MEMORY_DB_PATH)
    # Phase 2 slice 2.4c-B (docs/learning/PHASE2_DESIGN.md): the institutional
    # library, which organ 43 governs, is the only skill store. The legacy
    # `procedural_skills` store is attached READ-ONLY, as history, and nothing
    # promotes itself: activation is the operator's act.
    repository = SkillRepository(config.OPERATIONAL_STATE_DB_PATH)
    skills = build_skills_slot(
        repository=repository,
        trails=SkillTrailIndex(repository.database),
        history=SkillMemory(read_only=True),
    )
    # Reflexes compile and replay only from skills the operator activated, with
    # exactly the activated steps. Always attached: there is no ungated mode.
    cerebellum.attach_reflex_gate(skills)
    # Plan Phase 3b (docs/learning/PHASE3_DESIGN.md): learned rows this process
    # writes carry signed provenance, as LIVE rows. The seed is read from the
    # environment once, here; without it every record is unsigned, and an
    # unsigned row is never recalled (3c). Nothing generates a key.
    # A new state of an existing row is signed only if the state it extends
    # verifies under a PINNED key, so an unsigned row is never laundered into
    # a signed one by the next real event that touches it.
    pinned = LearningVerifier.from_pinned_file()
    provenance = ProvenanceWriter(
        ProvenanceStore(config.MEMORY_DB_PATH),
        LearningSigner.from_env(),
        source_kind="live",
        verifier=pinned,
    )
    # Plan Phase 3c: recall into a live turn admits only rows whose newest
    # record verifies under a pinned LIVE key. With no pinned key nothing is
    # admitted: recall is quiet until rows are re-earned or re-admitted.
    gate = RecallGate(provenance.store, pinned, context="live")
    adapters = {
        "working": WorkingMemoryAdapter(WorkingMemory()),
        "episodic": EpisodicMemoryAdapter(EpisodicMemory()),
        "semantic": LegacySemanticMemoryAdapter(
            SemanticMemory(config.MEMORY_DB_PATH), provenance=provenance, gate=gate
        ),
        "facts": SemanticFactsAdapter(
            SemanticFacts(), provenance=provenance, gate=gate
        ),
        "skills": skills,
        "lessons": MistakeMemoryAdapter(
            MistakeMemory(), provenance=provenance, gate=gate
        ),
        "development": DevelopmentHistoryAdapter(DevelopmentTracker()),
        "cerebellum": CerebellumAdapter(cerebellum),
        "curriculum": CurriculumAdapter(CurriculumManager(config.MEMORY_DB_PATH)),
    }
    authority = MemoryAuthority(
        store=MemoryAuthorityStore(config.MEMORY_DB_PATH),
        adapters=adapters,
    )
    consolidation = MemoryConsolidationAdapter(
        MemoryConsolidator(
            semantic=adapters["semantic"].store,
            mistakes=adapters["lessons"].store,
            facts=adapters["facts"].store,
            memory_authority=authority,
        )
    )
    authority.register_adapter("consolidation", consolidation)
    sync_pheromone_adapter(authority)
    consolidation.bind_authority(authority)
    return authority


def sync_pheromone_adapter(authority: MemoryAuthority) -> None:
    """Keep the advisory pheromone adapter aligned with live configuration."""
    if not config.PHEROMONE_ENABLED:
        authority.pheromone_adapter = None
        return
    current = getattr(authority.pheromone_adapter, "store", None)
    configured_path = str(config.PHEROMONE_DB)
    if (
        isinstance(authority.pheromone_adapter, AdvisoryPheromoneAdapter)
        and current is not None
        and str(getattr(current, "_db_path", "")) == configured_path
        and getattr(current, "_lambda", None) == config.PHEROMONE_LAMBDA_DECAY
        and getattr(current, "_floor", None) == config.PHEROMONE_FLOOR
    ):
        return
    from aios.memory.pheromones import PheromoneStore

    authority.pheromone_adapter = AdvisoryPheromoneAdapter(
        PheromoneStore(
            db_path=config.PHEROMONE_DB,
            lambda_decay=config.PHEROMONE_LAMBDA_DECAY,
            floor=config.PHEROMONE_FLOOR,
        )
    )


def build_council_memory_scope(
    authority: MemoryAuthority, runtime_root: str | Path
) -> tuple["CouncilState", "CouncilMemory", MemoryAuthority]:
    """Compose the mission-local Council memory scope from the authority.

    Council evidence is isolated per runtime root, so it must not be
    attached to the process-wide registry.  The copied authority keeps
    every shared adapter intact while the scoped Council adapter owns the
    exact mission-local store.
    """
    from aios.application.memory.adapters import CouncilMemoryAdapter
    from aios.council.council_memory import CouncilMemory
    from aios.council.council_state import CouncilState

    root = Path(runtime_root)
    council_state = CouncilState(db_path=root / "council_state.db")
    council_memory = CouncilMemory(state=council_state)
    scoped = authority.with_adapter("council", CouncilMemoryAdapter(council_memory))
    return council_state, council_memory, scoped
