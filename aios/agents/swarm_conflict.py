"""Conflict resolution for ant-colony swarm intelligence.

When multiple agents propose different solutions to the same problem,
this module provides mediation strategies:
1. **Merge** — combine compatible proposals
2. **Vote** — plurality/majority voting among agents
3. **Arbitrate** — domain-expert agent decides
4. **Escalate** — human-in-the-loop for critical conflicts
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ConflictResolution(Enum):
    MERGE = auto()
    VOTE = auto()
    ARBITRATE = auto()
    ESCALATE = auto()


@dataclass
class Proposal:
    """A single agent's proposed solution."""
    
    agent_id: str
    content: str
    confidence: float = 0.5           # 0.0 - 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def fingerprint(self) -> str:
        """Content hash for deduplication."""
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]
    
    def similarity_to(self, other: "Proposal") -> float:
        """Jaccard-like similarity between two proposals (0.0 - 1.0)."""
        if not self.content or not other.content:
            return 0.0
        
        words_a = set(self.content.lower().split())
        words_b = set(other.content.lower().split())
        
        if not words_a or not words_b:
            return 0.0
        
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)


@dataclass  
class ConflictReport:
    """Report of a resolved or escalated conflict."""
    
    proposals: List[Proposal]
    resolution: ConflictResolution
    result: Optional[str] = None
    winner_agent_id: Optional[str] = None
    merged_from: List[str] = field(default_factory=list)
    human_needed: bool = False
    reason: str = ""


class ConflictResolver:
    """Resolves conflicts between competing agent proposals."""
    
    # Similarity threshold for merge compatibility
    MERGE_SIMILARITY_THRESHOLD = 0.7
    
    # Minimum confidence for auto-acceptance
    AUTO_ACCEPT_CONFIDENCE = 0.85
    
    # Minimum confidence spread to trigger voting
    VOTE_SPREAD_THRESHOLD = 0.2
    
    def __init__(
        self,
        merge_threshold: float = 0.7,
        auto_accept_confidence: float = 0.85,
        human_escalation_threshold: int = 3,  # Max conflicts before human needed
    ):
        self.merge_threshold = merge_threshold
        self.auto_accept_confidence = auto_accept_confidence
        self.human_escalation_threshold = human_escalation_threshold
        self._conflict_count = 0
        self._escalation_callbacks: List[Callable] = []
    
    def resolve(
        self,
        proposals: List[Proposal],
        context: Optional[Dict[str, Any]] = None,
    ) -> ConflictReport:
        """Resolve a set of competing proposals."""
        if not proposals:
            return ConflictReport(
                proposals=[], 
                resolution=ConflictResolution.VOTE,
                result="",
                reason="No proposals to resolve"
            )
        
        if len(proposals) == 1:
            p = proposals[0]
            return ConflictReport(
                proposals=proposals,
                resolution=ConflictResolution.VOTE,
                result=p.content,
                winner_agent_id=p.agent_id,
                reason="Single proposal — unanimous"
            )
        
        self._conflict_count += 1
        
        # Check if we need human escalation (too many conflicts)
        if self._conflict_count > self.human_escalation_threshold:
            logger.warning(f"Conflict #{self._conflict_count}: escalating to human")
            return self._escalate(proposals, "Too many unresolved conflicts")
        
        # Check for clear winner (high confidence outlier)
        confidences = [p.confidence for p in proposals]
        max_conf = max(confidences)
        avg_conf = sum(confidences) / len(confidences)
        
        if max_conf >= self.auto_accept_confidence and (max_conf - avg_conf) > self.VOTE_SPREAD_THRESHOLD:
            winner = max(proposals, key=lambda p: p.confidence)
            logger.info(f"Auto-accepting proposal from {winner.agent_id} (confidence={max_conf:.2f})")
            return ConflictReport(
                proposals=proposals,
                resolution=ConflictResolution.ARBITRATE,
                result=winner.content,
                winner_agent_id=winner.agent_id,
                reason=f"Clear winner with confidence {max_conf:.2f}"
            )
        
        # Try merge first — find compatible proposal groups
        merge_groups = self._find_merge_groups(proposals)
        if merge_groups and len(merge_groups) < len(proposals):
            merged = self._merge_groups(merge_groups)
            if len(merged) == 1:
                logger.info(f"All proposals merged into single solution")
                return ConflictReport(
                    proposals=proposals,
                    resolution=ConflictResolution.MERGE,
                    result=merged[0],
                    merged_from=[p.agent_id for p in proposals],
                    reason="All proposals were compatible and merged"
                )
            else:
                # Some merged, some not — vote on merged results
                return self._vote(merged, proposals)
        
        # No mergeable groups — vote
        return self._vote(proposals, proposals)
    
    def _find_merge_groups(
        self, 
        proposals: List[Proposal]
    ) -> List[List[Proposal]]:
        """Group proposals that are similar enough to merge."""
        if not proposals:
            return []
        
        # Union-find for grouping
        parent = list(range(len(proposals)))
        
        def find(i):
            if parent[i] != i:
                parent[i] = find(parent[i])
            return parent[i]
        
        def union(i, j):
            pi, pj = find(i), find(j)
            if pi != pj:
                parent[pi] = pj
        
        # Group by similarity
        for i in range(len(proposals)):
            for j in range(i + 1, len(proposals)):
                if proposals[i].similarity_to(proposals[j]) >= self.merge_threshold:
                    union(i, j)
        
        # Build groups
        groups: Dict[int, List[Proposal]] = {}
        for i, p in enumerate(proposals):
            root = find(i)
            if root not in groups:
                groups[root] = []
            groups[root].append(p)
        
        return list(groups.values())
    
    def _merge_groups(self, groups: List[List[Proposal]]) -> List[str]:
        """Merge compatible proposals within each group."""
        merged: List[str] = []
        for group in groups:
            if len(group) == 1:
                merged.append(group[0].content)
            else:
                # Merge: take the most detailed (longest) as base
                base = max(group, key=lambda p: len(p.content))
                
                # Enhance with unique elements from others
                enhanced = base.content
                for other in group:
                    if other.agent_id == base.agent_id:
                        continue
                    # Add unique parts (simple heuristic: lines not in base)
                    base_lines = set(enhanced.splitlines())
                    for line in other.content.splitlines():
                        if line not in base_lines and len(line.strip()) > 10:
                            enhanced += f"\n# Merged from {other.agent_id}:\n{line}"
                
                merged.append(enhanced)
        
        return merged
    
    def _vote(
        self,
        candidates: List[Any],
        original_proposals: List[Proposal],
    ) -> ConflictReport:
        """Conduct weighted voting among candidates."""
        if not candidates:
            return self._escalate(original_proposals, "No candidates after merge")
        
        if len(candidates) == 1:
            winner = candidates[0]
            content = winner.content if isinstance(winner, Proposal) else str(winner)
            return ConflictReport(
                proposals=original_proposals,
                resolution=ConflictResolution.VOTE,
                result=content,
                reason="Single candidate after merge"
            )
        
        # Weighted vote: confidence-weighted
        votes: Dict[str, float] = {}
        agent_to_candidate: Dict[str, Any] = {}
        
        for proposal in original_proposals:
            # Find the most similar candidate
            best_candidate = None
            best_score = -1
            for i, candidate in enumerate(candidates):
                candidate_content = candidate.content if isinstance(candidate, Proposal) else str(candidate)
                score = proposal.similarity_to(Proposal("", candidate_content))
                if score > best_score:
                    best_score = score
                    best_candidate = i
            
            if best_candidate is not None:
                candidate_key = str(best_candidate)
                votes[candidate_key] = votes.get(candidate_key, 0.0) + proposal.confidence
                agent_to_candidate[candidate_key] = candidates[best_candidate]
        
        if not votes:
            return self._escalate(original_proposals, "No votes cast")
        
        # Winner takes all
        winner_key = max(votes, key=lambda k: votes[k])
        winner = agent_to_candidate[winner_key]
        result = winner.content if isinstance(winner, Proposal) else str(winner)
        
        # Find which original agent contributed most to winning candidate
        winner_agent = None
        best_score = -1
        for p in original_proposals:
            score = p.similarity_to(Proposal("", result))
            if score > best_score:
                best_score = score
                winner_agent = p.agent_id
        
        total_votes = sum(votes.values())
        logger.info(
            f"Vote result: candidate {winner_key} wins "
            f"({votes[winner_key]:.2f}/{total_votes:.2f} votes)"
        )
        
        return ConflictReport(
            proposals=original_proposals,
            resolution=ConflictResolution.VOTE,
            result=result,
            winner_agent_id=winner_agent,
            reason=f"Won vote with {votes[winner_key]:.1f}/{total_votes:.1f} confidence-weighted votes"
        )
    
    def _escalate(
        self,
        proposals: List[Proposal],
        reason: str,
    ) -> ConflictReport:
        """Escalate to human-in-the-loop."""
        logger.warning(f"Escalating conflict to human: {reason}")
        
        # Trigger escalation callbacks
        for cb in self._escalation_callbacks:
            try:
                cb(proposals, reason)
            except Exception:
                pass
        
        return ConflictReport(
            proposals=proposals,
            resolution=ConflictResolution.ESCALATE,
            human_needed=True,
            reason=reason,
        )
    
    def on_escalation(self, callback: Callable) -> None:
        """Register a callback for human escalation events."""
        self._escalation_callbacks.append(callback)
    
    def reset_counter(self) -> None:
        """Reset the conflict counter (call after successful resolution cycle)."""
        self._conflict_count = 0


# ─── Higher-level orchestration ──────────────────────────────────────────────

class SwarmMediator:
    """High-level mediator that orchestrates conflict resolution across tasks."""
    
    def __init__(self, resolver: Optional[ConflictResolver] = None):
        self.resolver = resolver or ConflictResolver()
        self._resolution_log: List[ConflictReport] = []
    
    def mediate(
        self,
        task_id: str,
        proposals: List[Proposal],
        context: Optional[Dict[str, Any]] = None,
    ) -> ConflictReport:
        """Mediate a conflict and log the result."""
        logger.info(f"Mediating task {task_id} with {len(proposals)} proposals")
        
        report = self.resolver.resolve(proposals, context)
        report.metadata = {"task_id": task_id, **(context or {})}
        
        self._resolution_log.append(report)
        
        if report.resolution == ConflictResolution.ESCALATE:
            logger.warning(f"Task {task_id} escalated to human")
        else:
            logger.info(
                f"Task {task_id} resolved via {report.resolution.name}: "
                f"winner={report.winner_agent_id}"
            )
        
        return report
    
    @property
    def escalation_rate(self) -> float:
        """Fraction of conflicts that required human escalation."""
        if not self._resolution_log:
            return 0.0
        escalated = sum(1 for r in self._resolution_log if r.human_needed)
        return escalated / len(self._resolution_log)
    
    @property
    def merge_rate(self) -> float:
        """Fraction of conflicts resolved via merging."""
        if not self._resolution_log:
            return 0.0
        merged = sum(1 for r in self._resolution_log if r.resolution == ConflictResolution.MERGE)
        return merged / len(self._resolution_log)
