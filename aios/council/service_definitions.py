"""Shared service definitions for the simulated Council Runtime."""
from __future__ import annotations

from typing import Protocol

from aios.runtime.contracts import MissionContract, QueenVerdict


class ContractQueen(Protocol):
    """Minimal protocol for queens that review MissionContracts."""

    name: str

    def review(self, contract: MissionContract) -> QueenVerdict:
        ...


__all__ = ["ContractQueen"]
