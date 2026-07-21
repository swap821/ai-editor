"""Provider adapter boundary.

Concrete Ollama/cloud clients remain in ``aios.core`` for compatibility. The
application ModelRouter receives them as capability-limited client objects so
Queens and workers do not import provider implementations directly.
"""

from typing import Protocol


class CompletionProvider(Protocol):
    def complete(self, prompt: str, *, system: str | None = None) -> str: ...


__all__ = ["CompletionProvider"]
