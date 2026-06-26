"""Dynamic swarm size adaptation for the ant-colony swarm.

Scales the number of workers based on task complexity estimates:
- Simple tasks  → 1–3 workers
- Medium tasks  → 4–7 workers  
- Complex tasks → 8–15 workers

Uses a Boltzmann-inspired acceptance criterion to allow
occasional exploration of larger swarm sizes.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ComplexityProfile:
    """Describes the computational complexity of a task."""
    
    estimated_steps: int           # Rough step count
    branching_factor: float = 1.0  # How many paths per step
    io_heavy: bool = False         # Lots of network/disk?
    memory_intensive: bool = False # Large data structures?
    
    @property
    def score(self) -> float:
        """Compute a single complexity score (0-100)."""
        base = math.log10(max(self.estimated_steps, 10)) * 10
        branch_penalty = self.branching_factor * 5
        io_penalty = 15 if self.io_heavy else 0
        mem_penalty = 10 if self.memory_intensive else 0
        return min(base + branch_penalty + io_penalty + mem_penalty, 100)


class AdaptiveSwarmSizer:
    """Determines optimal swarm size using adaptive heuristics."""
    
    # Complexity thresholds
    SIMPLE_MAX = 25.0
    MEDIUM_MAX = 60.0
    
    # Base swarm sizes
    SIMPLE_RANGE = (1, 3)
    MEDIUM_RANGE = (4, 7)
    COMPLEX_RANGE = (8, 15)
    
    def __init__(
        self,
        temperature: float = 5.0,     # Boltzmann temperature for exploration
        history_window: int = 10,     # How many past results to remember
    ):
        self.temperature = temperature
        self.history_window = history_window
        self._performance_history: List[Dict] = []
    
    def size_for_task(
        self,
        profile: ComplexityProfile,
        available_workers: int = 50,
    ) -> int:
        """Recommend swarm size for a given task profile."""
        score = profile.score
        
        # Base range from complexity
        if score <= self.SIMPLE_MAX:
            base_range = self.SIMPLE_RANGE
        elif score <= self.MEDIUM_MAX:
            base_range = self.MEDIUM_RANGE
        else:
            base_range = self.COMPLEX_RANGE
        
        # Clamp to available workers
        lo, hi = base_range
        hi = min(hi, available_workers)
        lo = min(lo, hi)
        
        # Boltzmann exploration: occasionally pick outside the base range
        candidates = list(range(lo, hi + 1))
        
        if self.temperature > 0 and len(candidates) > 1:
            # Add exploratory candidates (up to 2x the range)
            exploratory = list(range(lo, min(hi * 2, available_workers) + 1))
            candidates = list(dict.fromkeys(candidates + exploratory))
            
            # Boltzmann weights: prefer middle of range
            mid = (lo + hi) / 2
            weights = []
            for c in candidates:
                energy = abs(c - mid)  # Distance from ideal
                prob = math.exp(-energy / self.temperature)
                weights.append(prob)
            
            return random.choices(candidates, weights=weights, k=1)[0]
        
        # No exploration — return middle of range
        return (lo + hi) // 2
    
    def record_result(
        self,
        swarm_size: int,
        profile: ComplexityProfile,
        success: bool,
        execution_time_ms: float,
    ) -> None:
        """Record performance of a swarm size choice for future tuning."""
        self._performance_history.append({
            "swarm_size": swarm_size,
            "complexity_score": profile.score,
            "success": success,
            "execution_time_ms": execution_time_ms,
        })
        
        # Trim history
        if len(self._performance_history) > self.history_window:
            self._performance_history = self._performance_history[-self.history_window:]
    
    @property
    def average_time_for_size(self, size: int) -> Optional[float]:
        """Get average execution time for a given swarm size."""
        times = [
            r["execution_time_ms"]
            for r in self._performance_history
            if r["swarm_size"] == size
        ]
        return sum(times) / len(times) if times else None


def default_sizer() -> AdaptiveSwarmSizer:
    """Factory for the default adaptive swarm sizer."""
    return AdaptiveSwarmSizer(temperature=5.0)


# ─── Complexity estimation helpers ───────────────────────────────────────────

def estimate_code_complexity(code: str) -> ComplexityProfile:
    """Estimate complexity from code string heuristics."""
    lines = code.splitlines()
    steps = len(lines)
    
    # Count control flow branching
    branch_keywords = ['if', 'for', 'while', 'try', 'with', 'match']
    branch_count = sum(1 for line in lines if any(kw in line for kw in branch_keywords))
    branching = max(1.0, branch_count / max(steps, 1) * 10)
    
    io_heavy = any(kw in code for kw in ['requests', 'open(', 'socket', 'db.', 'query'])
    memory_intensive = any(kw in code for kw in ['DataFrame', 'load(', 'read_csv', 'to_numpy'])
    
    return ComplexityProfile(
        estimated_steps=steps,
        branching_factor=branching,
        io_heavy=io_heavy,
        memory_intensive=memory_intensive,
    )


def estimate_task_complexity(task_description: str) -> ComplexityProfile:
    """Estimate complexity from a natural-language task description."""
    words = task_description.split()
    steps = len(words)
    
    # Keyword-based heuristics
    complexity_keywords = ['optimize', 'refactor', 'debug', 'architect', 'design']
    complex_score = sum(1 for kw in complexity_keywords if kw in task_description.lower())
    branching = 1.0 + complex_score * 0.5
    
    io_heavy = any(kw in task_description.lower() for kw in ['fetch', 'download', 'api', 'database'])
    memory_intensive = any(kw in task_description.lower() for kw in ['analyze', 'process', 'transform', 'large'])
    
    return ComplexityProfile(
        estimated_steps=max(steps, 10),
        branching_factor=branching,
        io_heavy=io_heavy,
        memory_intensive=memory_intensive,
    )
