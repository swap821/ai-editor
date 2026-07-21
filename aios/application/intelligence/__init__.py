"""Application-level compilation of governed intelligence context."""

from .context_compiler import CompilationTarget, compile_representative_context
from .gateway import (
    IntelligenceGatewayError,
    IntelligenceGatewayResult,
    route_intelligence_request,
)

__all__ = [
    "CompilationTarget",
    "IntelligenceGatewayError",
    "IntelligenceGatewayResult",
    "compile_representative_context",
    "route_intelligence_request",
]
