"""GAGOS — a local-first, memory-driven, security-gated, human-supervised AI operating system.

Package layout
--------------
``aios.core``      Planner, confidence filter, scope-constrained executor, verifier.
``aios.memory``    Four-layer memory (working/episodic/semantic/mistake) plus
                   hybrid BM25 + FAISS retrieval — the "hippocampus".
``aios.security``  Deterministic 3-zone gateway, scope lock, secret scanner, and
                   the SHA-256 hash-chained audit logger.
``aios.agents``    Higher-order agents: reflection (post-mortem learning) and
                   rollback (git-stash + file snapshot).
``aios.api``       FastAPI orchestration layer exposing the core endpoints.

All tunables (paths, retrieval weights, security thresholds) live in
:mod:`aios.config`, the single source of truth for configuration.
"""
from __future__ import annotations

__version__ = "0.1.0"
