"""Prometheus-format observability metrics for the AI-OS.

All metrics live in a dedicated :class:`CollectorRegistry` so tests stay isolated
and no other library can accidentally pollute the scrape output.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, generate_latest

from aios.security.audit_logger import verify_chain


class MetricsCollector:
    """Collect and expose AI-OS operational metrics in Prometheus text format."""

    def __init__(self) -> None:
        self._build_metrics()

    def _build_metrics(self) -> None:
        """Create the registry and metric objects."""
        self.registry = CollectorRegistry()
        self._tasks = Gauge("aios_tasks_total", "Total recorded turn tasks", registry=self.registry)
        self._verified_success_rate = Gauge(
            "aios_verified_success_rate",
            "Ratio of verified outcomes that succeeded",
            registry=self.registry,
        )
        self._verification_coverage = Gauge(
            "aios_verification_coverage",
            "Ratio of recorded tasks with a verified outcome",
            registry=self.registry,
        )
        self._human_intervention_rate = Gauge(
            "aios_human_intervention_rate",
            "Ratio of tasks that required human intervention",
            registry=self.registry,
        )
        self._average_tool_calls = Gauge(
            "aios_average_tool_calls",
            "Average number of tool calls per task",
            registry=self.registry,
        )
        self._blocked_actions = Gauge(
            "aios_blocked_actions_total",
            "Total actions blocked by the security gateway",
            registry=self.registry,
        )
        self._lessons = Gauge(
            "aios_lessons_total", "Total recorded mistake lessons", registry=self.registry
        )
        self._repeated_mistakes = Gauge(
            "aios_repeated_mistakes_total",
            "Total occurrences of repeated mistakes",
            registry=self.registry,
        )
        self._approvals = Gauge(
            "aios_approvals_total", "Total issued approval grants", registry=self.registry
        )
        self._earned_autonomy = Gauge(
            "aios_earned_autonomy_grants_total",
            "Total earned-autonomy signatures currently granted",
            registry=self.registry,
        )
        self._audit_chain_valid = Gauge(
            "aios_audit_chain_valid",
            "1 if the tamper-evident audit hash chain is valid, 0 otherwise",
            registry=self.registry,
        )
        self._audit_verify_failures = Counter(
            "aios_audit_verify_failures_total",
            "Times the audit hash-chain verification endpoint detected tampering",
            registry=self.registry,
        )

    def update(
        self,
        summary: dict[str, Any],
        approvals_count: int,
        earned_autonomy_count: int,
        audit_db_path: Optional[Path] = None,
    ) -> None:
        """Refresh all gauges from the latest subsystem state."""
        tasks = int(summary.get("tasks") or 0)
        self._tasks.set(tasks)
        self._verified_success_rate.set(
            float(summary.get("verified_success_rate") or 0.0)
        )
        self._verification_coverage.set(float(summary.get("verification_coverage") or 0.0))
        self._human_intervention_rate.set(
            float(summary.get("human_intervention_rate") or 0.0)
        )
        self._average_tool_calls.set(float(summary.get("average_tool_calls") or 0.0))
        self._blocked_actions.set(int(summary.get("blocked_actions") or 0))
        self._lessons.set(int(summary.get("lessons") or 0))
        self._repeated_mistakes.set(int(summary.get("repeated_mistakes") or 0))
        self._approvals.set(int(approvals_count))
        self._earned_autonomy.set(int(earned_autonomy_count))

        status = verify_chain(db_path=audit_db_path) if audit_db_path else verify_chain()
        self._audit_chain_valid.set(1.0 if status.valid else 0.0)

    def record_audit_verify_failure(self) -> None:
        """Increment the audit-verify-failure counter."""
        self._audit_verify_failures.inc()

    def clear(self) -> None:
        """Recreate the registry and metrics so tests start from a clean slate."""
        self._build_metrics()


def get_collector() -> MetricsCollector:
    """Return the process-wide metrics collector."""
    return _COLLECTOR


_COLLECTOR = MetricsCollector()
