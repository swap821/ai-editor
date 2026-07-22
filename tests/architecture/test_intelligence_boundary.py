"""Architecture tests for the Canonical Intelligence Boundary.

This test enforces that intelligence providers (cloud and local LLMs) are 
not instantiated directly by application or agent code, bypassing the 
governed ModelRouter and PrivacyBroker.
"""
import ast
import os
import pytest

# Only these core routing and dependency injection modules are allowed
# to import and instantiate the raw provider adapters.
ALLOWED_CLIENT_IMPORTERS = {
    "aios/api/deps.py",
    "aios/core/router_wiring.py",
    "aios/core/llm.py",
    "aios/core/bedrock.py",
    "aios/core/gemini.py",
    "aios/core/openai_compat.py",
    "aios/core/anthropic_direct.py",
    "aios/api/main.py",          # Legacy compat, needs migration
    "aios/api/routes/models.py", # Legacy compat, needs migration
    "aios/core/failover.py",
    # Slice 30: local-model adapters. Each constructs an OllamaClient bound
    # to one specific local model/host/params combination -- there is no
    # shared singleton to reuse across different local models the way cloud
    # providers reuse one client per provider. These are provider-adapter
    # factories in the sense the boundary is meant to allow, not bypasses.
    "aios/domain/local_workforce/registry.py",
    "aios/application/local_workforce/service.py",
    "aios/runtime/intelligence_gateway.py",
    # isinstance(self.llm, OllamaClient) capability check on an injected
    # client (self.llm = llm at construction) -- not a construction site.
    "aios/agents/reflection_agent.py",
    # Slice 41: default local-model provider for Council Planner/King
    # reasoning, wired through route_intelligence_request() (Slice 30)
    # rather than calling a provider directly -- same category as the
    # local-model adapters above, not a boundary bypass.
    "aios/council/gateway_reasoning.py",
}

# Provider adapter classes that should not be used directly.
FORBIDDEN_CLASSES = {
    "BedrockClient",
    "GeminiClient",
    "AnthropicDirectClient",
    "OpenAICompatClient",
    "OllamaClient",
}

def _iter_python_files(root_dir: str):
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".py"):
                yield os.path.join(dirpath, filename)

@pytest.mark.architecture
def test_no_direct_cloud_client_instantiation():
    """Ensure that application code does not bypass the hiring broker.

    Cloud clients must be obtained through the ModelRouter or the 
    legacy _select_chat_client, never instantiated directly.
    """
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../aios"))
    violations = []
    
    for filepath in _iter_python_files(root):
        rel_path = os.path.relpath(filepath, os.path.dirname(root)).replace("\\", "/")
        if rel_path in ALLOWED_CLIENT_IMPORTERS:
            continue
            
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
            
        # Check imports
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in FORBIDDEN_CLASSES:
                        violations.append(f"{rel_path}:{node.lineno} imports {alias.name}")
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in FORBIDDEN_CLASSES:
                    violations.append(f"{rel_path}:{node.lineno} references {node.id}")
                    
    assert not violations, "Direct cloud client usage detected outside allowed boundaries:\n" + "\n".join(violations)
