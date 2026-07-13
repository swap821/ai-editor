"""Structured control-plane to executor-service contracts."""

from .protocol import (
    ExecutorCapability,
    ExecutorJob,
    ExecutorResult,
    MountPolicy,
    NetworkPolicy,
    ResourceLimits,
)

__all__ = [
    "ExecutorCapability",
    "ExecutorJob",
    "ExecutorResult",
    "MountPolicy",
    "NetworkPolicy",
    "ResourceLimits",
]
