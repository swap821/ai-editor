"""Incremental read-model application services."""

from aios.application.read_models.projection import (
    IncrementalSystemProjection,
    SystemProjectionConsumer,
    get_system_projection,
)

__all__ = [
    "IncrementalSystemProjection",
    "SystemProjectionConsumer",
    "get_system_projection",
]
