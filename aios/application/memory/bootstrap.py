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
    DevelopmentHistoryAdapter,
    EpisodicMemoryAdapter,
    LegacySemanticMemoryAdapter,
    MemoryConsolidationAdapter,
    MistakeMemoryAdapter,
    SemanticFactsAdapter,
    SkillMemoryAdapter,
    WorkingMemoryAdapter,
)
from aios.application.memory.authority import MemoryAuthority
from aios.infrastructure.memory import MemoryAuthorityStore
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.development import DevelopmentTracker
from aios.memory.episodic import EpisodicMemory
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
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
    adapters = {
        "working": WorkingMemoryAdapter(WorkingMemory()),
        "episodic": EpisodicMemoryAdapter(EpisodicMemory()),
        "semantic": LegacySemanticMemoryAdapter(SemanticMemory(config.MEMORY_DB_PATH)),
        "facts": SemanticFactsAdapter(SemanticFacts()),
        "skills": SkillMemoryAdapter(SkillMemory()),
        "lessons": MistakeMemoryAdapter(MistakeMemory()),
        "development": DevelopmentHistoryAdapter(DevelopmentTracker()),
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
