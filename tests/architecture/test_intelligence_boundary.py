"""Architecture tests for the Canonical Intelligence Boundary.

This test enforces that intelligence providers (cloud and local LLMs) are 
not instantiated directly by application or agent code, bypassing the 
governed ModelRouter and PrivacyBroker.
"""
import ast
import os
import pytest

from aios import config

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
}

# Provider adapter classes that should not be used directly.
FORBIDDEN_CLASSES = {
    "BedrockClient",
    "GeminiClient",
    "AnthropicDirectClient",
    "OpenAICompatClient",
}

def _iter_python_files(root_dir: str):
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".py"):
                yield os.path.join(dirpath, filename)

@pytest.mark.architecture
@pytest.mark.xfail(reason="Pending Phase 1 of Intelligence Migration (Slice 3)")
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
                    
    # Note: generate_pipeline.py currently violates this by instantiating BedrockClient
    # and GeminiClient directly. This test will fail until Phase 1 of the migration
    # is complete. We expect it to fail as proof of the boundary violation.
    assert not violations, "Direct cloud client usage detected outside allowed boundaries:\n" + "\n".join(violations)

