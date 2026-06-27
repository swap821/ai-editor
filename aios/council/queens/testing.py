"""Testing Queen wrapper around verification evidence and Verifier."""
from __future__ import annotations

from typing import Any

from aios.core.verifier import Verifier
from aios.runtime.contracts import MissionContract, QueenVerdict, RunLedger


class TestingQueen:
    """Verify reality after worker execution."""

    name = "testing"

    def __init__(self, verifier: Verifier | None = None) -> None:
        self.verifier = verifier

    def verify(
        self,
        *,
        contract: MissionContract,
        ledger: RunLedger | None = None,
        approved: bool = True,
        session_id: str | None = None,
    ) -> QueenVerdict:
        if self.verifier is not None and contract.verification_commands:
            return self._verify_live(
                contract=contract,
                approved=approved,
                session_id=session_id,
            )
        return self._verify_ledger(contract=contract, ledger=ledger)

    def _verify_live(
        self,
        *,
        contract: MissionContract,
        approved: bool,
        session_id: str | None,
    ) -> QueenVerdict:
        results: list[dict[str, Any]] = []
        for command in contract.verification_commands:
            result = self.verifier.verify(
                command,
                approved=approved,
                session_id=session_id,
            )
            results.append(
                {
                    "command": command,
                    "passed": result.passed,
                    "summary": result.summary,
                    "exit_code": result.exit_code,
                    "status": result.status,
                }
            )
        return self._verdict_from_results(results, mode="verifier")

    def _verify_ledger(
        self,
        *,
        contract: MissionContract,
        ledger: RunLedger | None,
    ) -> QueenVerdict:
        commands = []
        if ledger is not None:
            commands = list(ledger.verification.get("commands", []))
        if not contract.verification_commands and not commands:
            return QueenVerdict(
                queen=self.name,
                verdict="defer",
                risk="YELLOW",
                reason="No verification command or evidence was provided.",
                constraints=["Add verification_commands before trusting the mission."],
                confidence=0.78,
                metadata={"mode": "ledger", "verification": []},
            )
        results = [
            {
                "command": item.get("command"),
                "passed": item.get("returncode") == 0,
                "summary": (item.get("stdout") or item.get("stderr") or "")[-500:],
                "exit_code": item.get("returncode"),
                "status": "OK",
            }
            for item in commands
        ]
        return self._verdict_from_results(results, mode="ledger")

    def _verdict_from_results(
        self,
        results: list[dict[str, Any]],
        *,
        mode: str,
    ) -> QueenVerdict:
        if not results:
            return QueenVerdict(
                queen=self.name,
                verdict="defer",
                risk="YELLOW",
                reason="Testing Queen found no verification results.",
                constraints=["Run at least one verification command."],
                confidence=0.75,
                metadata={"mode": mode, "verification": results},
            )
        failed = [result for result in results if not result["passed"]]
        if failed:
            return QueenVerdict(
                queen=self.name,
                verdict="deny",
                risk="YELLOW",
                reason=f"{len(failed)} verification command(s) failed.",
                constraints=["Revise the mission before King approval."],
                confidence=0.92,
                metadata={"mode": mode, "verification": results},
            )
        return QueenVerdict(
            queen=self.name,
            verdict="allow",
            risk="GREEN",
            reason=f"{len(results)} verification command(s) passed.",
            constraints=[],
            confidence=0.9,
            metadata={"mode": mode, "verification": results},
        )


__all__ = ["TestingQueen"]
