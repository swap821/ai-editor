"""Resource admission gate for local clerical models."""

from __future__ import annotations

import os
from typing import Dict, Any

from pydantic import BaseModel

from aios import config


class AdmissionContext(BaseModel):
    """Contextual information needed to make an admission decision."""

    requested_context_size: int
    requested_output_size: int
    active_docker_workload: int = 0
    active_local_inference_count: int = 0


class AdmissionResult(BaseModel):
    """The result of the resource admission gate."""

    admitted: bool
    reason: str | None = None
    system_metrics: Dict[str, Any]


class HardwareAdmission:
    """Evaluates whether the local hardware has capacity for a local model."""

    def __init__(
        self,
        min_cpu_count: int = 2,
        max_concurrent_inferences: int = 2,
    ) -> None:
        self.min_cpu_count = min_cpu_count
        self.max_concurrent_inferences = max_concurrent_inferences

    def evaluate(self, context: AdmissionContext) -> AdmissionResult:
        """Evaluate if the system has capacity for the requested model."""
        cpu_count = os.cpu_count() or 1

        metrics = {
            "cpu_count": cpu_count,
            "active_inferences": context.active_local_inference_count,
            "active_docker_workload": context.active_docker_workload,
        }

        if cpu_count < self.min_cpu_count:
            return AdmissionResult(
                admitted=False,
                reason=f"Insufficient CPU cores: {cpu_count} < {self.min_cpu_count}",
                system_metrics=metrics,
            )

        if context.active_local_inference_count >= self.max_concurrent_inferences:
            return AdmissionResult(
                admitted=False,
                reason=f"Too many active local inferences: {context.active_local_inference_count}",
                system_metrics=metrics,
            )

        return AdmissionResult(
            admitted=True,
            reason=None,
            system_metrics=metrics,
        )
