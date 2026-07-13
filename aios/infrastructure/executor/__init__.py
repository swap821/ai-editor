"""Infrastructure implementations for the isolated Executor Service."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .docker_runner import DockerJobRunner


def __getattr__(name: str):
    """Load the Docker adapter lazily to keep validator imports acyclic."""
    if name == "DockerJobRunner":
        from .docker_runner import DockerJobRunner

        return DockerJobRunner
    raise AttributeError(name)


__all__ = ["DockerJobRunner"]
