"""Unit tests for automatic model selection (aios.core.model_selector).

The selector is a pure, deterministic heuristic — no Ollama, no network — so the
"which model is best" policy is pinned by tests instead of living in the UI.
"""
from __future__ import annotations

from aios.core.model_selector import (
    describe_choice,
    infer_task,
    is_base_model,
    is_tool_capable,
    parse_size_b,
    select_model,
    supports_tool_protocol,
)


def test_empty_or_none_returns_none() -> None:
    assert select_model([]) is None
    assert select_model(None) is None


def test_excludes_embedding_and_vision_models() -> None:
    # An install with only non-chat models has nothing to drive the agent loop.
    assert select_model(["nomic-embed-text:latest", "llava:7b"]) is None
    # ...and an embedder never wins over a real chat model.
    assert select_model(["nomic-embed-text:latest", "llama3.1:8b"]) == "llama3.1:8b"


def test_coder_beats_a_larger_general_model() -> None:
    # For the agentic CODE-edit loop a coder-tuned model is preferred over a
    # bigger general one — capability for the task outranks raw size.
    assert select_model(["llama3.1:8b", "qwen2.5-coder:3b"]) == "qwen2.5-coder:3b"


def test_base_model_is_demoted_below_instruct() -> None:
    # A non-instruct 'base' coder model is a poor chat/tool driver; an instruct
    # general model is chosen ahead of it despite the coder family.
    assert select_model(["qwen2.5-coder:1.5b-base", "llama3.2:3b"]) == "llama3.2:3b"
    assert is_base_model("qwen2.5-coder:1.5b-base") is True
    assert is_base_model("qwen2.5-coder:3b") is False


def test_size_breaks_ties_within_a_family() -> None:
    assert select_model(["qwen2.5-coder:3b", "qwen2.5-coder:7b"]) == "qwen2.5-coder:7b"
    assert select_model(["llama3.1:8b", "llama3.1:70b"]) == "llama3.1:70b"


def test_real_installed_set_picks_qwen_coder_7b() -> None:
    # The operator's actual `ollama list`: the agent should auto-select the
    # strongest coder, not a general/reasoning/embed/base model.
    installed = [
        "mistral:7b",
        "deepseek-r1:8b",
        "qwen2.5:7b",
        "qwen2.5-coder:7b",
        "qwen2.5-coder:3b",
        "nomic-embed-text:latest",
        "llama3.2:3b",
        "qwen2.5-coder:1.5b-base",
        "llama3.1:8b",
    ]
    assert select_model(installed) == "qwen2.5-coder:7b"


def test_parse_size_and_describe_choice() -> None:
    assert parse_size_b("qwen2.5-coder:3b") == 3.0
    assert parse_size_b("qwen2.5-coder:1.5b-base") == 1.5
    assert parse_size_b("llama3.1:8b") == 8.0
    assert parse_size_b("some-model:latest") == 0.0
    assert describe_choice("qwen2.5-coder:3b") == "coder-tuned, 3B, instruct"
    assert "base" in describe_choice("qwen2.5-coder:1.5b-base")


def test_selection_is_deterministic() -> None:
    installed = ["llama3.2:3b", "qwen2.5-coder:3b", "llama3.1:8b"]
    picks = {select_model(installed) for _ in range(5)}
    assert picks == {"qwen2.5-coder:3b"}


# --------------------------------------------------------------------------- #
# task-aware routing — the agent picks the right model for the PURPOSE
# --------------------------------------------------------------------------- #
def test_coding_task_prefers_the_coder() -> None:
    installed = ["qwen2.5-coder:7b", "qwen2.5:7b", "deepseek-r1:8b"]
    assert select_model(installed, task="coding") == "qwen2.5-coder:7b"


def test_reasoning_task_prefers_a_reasoning_model() -> None:
    installed = ["qwen2.5-coder:7b", "deepseek-r1:8b", "llama3.1:8b"]
    assert select_model(installed, task="reasoning") == "deepseek-r1:8b"


def test_general_task_prefers_strong_general_over_coder() -> None:
    installed = ["qwen2.5-coder:7b", "qwen2.5:7b", "llama3.2:3b"]
    assert select_model(installed, task="general") == "qwen2.5:7b"


def test_fast_task_prefers_the_smallest_capable_model() -> None:
    installed = ["llama3.1:8b", "llama3.2:3b", "qwen2.5:7b"]
    assert select_model(installed, task="fast") == "llama3.2:3b"


def test_require_tools_excludes_reasoning_and_base_families() -> None:
    # A reasoning model is great for analysis but can't drive the tool loop, so
    # the loop (require_tools) skips it — even for a reasoning task — and lands on
    # the best TOOL-CAPABLE model. Base models are excluded too.
    assert is_tool_capable("deepseek-r1:8b") is False
    assert is_tool_capable("qwen2.5-coder:1.5b-base") is False
    assert is_tool_capable("mistral:7b") is False
    assert supports_tool_protocol("mistral:7b") is True
    assert supports_tool_protocol("deepseek-r1:8b") is False
    assert supports_tool_protocol("nomic-embed-text:latest") is False
    assert is_tool_capable("qwen2.5-coder:7b") is True
    installed = ["deepseek-r1:8b", "qwen2.5-coder:1.5b-base", "qwen2.5:7b"]
    assert select_model(installed, task="reasoning", require_tools=True) == "qwen2.5:7b"
    # ...but unconstrained, reasoning routes to the reasoner.
    assert select_model(installed, task="reasoning") == "deepseek-r1:8b"


def test_mistral_remains_available_for_non_agentic_general_chat() -> None:
    assert select_model(["mistral:7b"], task="general") == "mistral:7b"
    assert select_model(["mistral:7b"], task="general", require_tools=True) is None


def test_infer_task_routes_by_message() -> None:
    assert infer_task("Use the edit_file tool to fix the bug in greeter.py") == "coding"
    assert infer_task("refactor this function and run the tests") == "coding"
    assert infer_task("analyze the trade-offs and plan the migration") == "reasoning"
    assert infer_task("why does this design scale poorly?") == "reasoning"
    assert infer_task("write a short welcome message for new users") == "general"
    assert infer_task("") == "general"
