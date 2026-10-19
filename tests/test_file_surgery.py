"""Unit tests for the resilient file surgery engine (aios/agents/file_surgery.py).

Verifies:
  - Tier 1: Exact string replacement
  - Tier 2: Whitespace and indentation normalized replacement
  - Tier 3: Fuzzy sequence-matcher replacement with threshold >= 0.92
  - Tier 4: AST-guided Python function/class replacement
  - Replay handling: Already-applied edits return replay status
  - Multiple match protection: Ambiguous targets fail-closed
  - Rich context hint generation on failure
"""

from __future__ import annotations

import pytest
from aios.agents.file_surgery import perform_file_surgery, SurgeryResult


SAMPLE_PYTHON_FILE = """import os
import sys

def calculate_total(items: list[dict]) -> float:
    total = 0.0
    for item in items:
        price = item.get("price", 0.0)
        qty = item.get("qty", 1)
        total += price * qty
    return total

def print_receipt(total: float) -> None:
    print(f"Receipt Total: ${total:.2f}")

if __name__ == "__main__":
    items = [{"price": 10.0, "qty": 2}, {"price": 5.5, "qty": 1}]
    print_receipt(calculate_total(items))
"""


def test_tier_1_exact_match():
    old_str = "    total = 0.0\n    for item in items:"
    new_str = "    total = 0.0\n    # Process all line items\n    for item in items:"
    res = perform_file_surgery(SAMPLE_PYTHON_FILE, old_str, new_str, "calc.py")
    assert res.status == "exact"
    assert res.tier == 1
    assert res.updated_content is not None
    assert "# Process all line items" in res.updated_content
    assert res.similarity == 1.0


def test_tier_2_whitespace_normalized_indent_drift():
    # Model indented with 8 spaces instead of 4 spaces
    drifted_old = "        total = 0.0\n        for item in items:"
    new_str = "    total = 0.0\n    # Fast path\n    for item in items:"
    res = perform_file_surgery(SAMPLE_PYTHON_FILE, drifted_old, new_str, "calc.py")
    assert res.status == "normalized"
    assert res.tier == 2
    assert res.updated_content is not None
    assert "# Fast path" in res.updated_content
    assert res.similarity >= 0.98


def test_tier_2_whitespace_crlf_and_trailing_spaces():
    # Old string with trailing spaces on line ends and CRLF line breaks
    crlf_old = "    total = 0.0   \r\n    for item in items:  \r\n"
    new_str = "    total = 0.0\n    # Cleaned\n    for item in items:\n"
    res = perform_file_surgery(SAMPLE_PYTHON_FILE, crlf_old, new_str, "calc.py")
    assert res.status == "normalized"
    assert res.tier == 2
    assert "# Cleaned" in res.updated_content


def test_tier_3_fuzzy_small_typo_drift():
    # Model had a tiny comment or typo in variable name: 'item' vs 'item_obj'
    drifted_old = """def print_receipt(total: float) -> None:
    print(f"Receipt Total: ${total:.2f}")"""
    # Let's drift one character: "Total:" -> "TOTAL:"
    fuzzy_old = """def print_receipt(total: float) -> None:
    print(f"Receipt TOTAL: ${total:.2f}")"""
    new_str = """def print_receipt(total: float) -> None:
    formatted = f"${total:.2f}"
    print(f"Grand Total: {formatted}")"""

    res = perform_file_surgery(SAMPLE_PYTHON_FILE, fuzzy_old, new_str, "calc.py")
    assert res.status == "fuzzy"
    assert res.tier == 3
    assert res.updated_content is not None
    assert "Grand Total:" in res.updated_content
    assert res.similarity >= 0.92


def test_tier_4_ast_python_function_replacement():
    # Model reconstructed the function signature and body slightly differently
    # but targets calculate_total
    old_fn = """def calculate_total(items: list[dict]) -> float:
    total = 0
    for it in items:
        total += it["price"] * it["qty"]
    return total"""
    new_fn = """def calculate_total(items: list[dict]) -> float:
    return sum(item.get("price", 0.0) * item.get("qty", 1) for item in items)"""

    res = perform_file_surgery(SAMPLE_PYTHON_FILE, old_fn, new_fn, "calc.py")
    assert res.status in ("ast", "fuzzy")
    assert res.updated_content is not None
    assert "return sum(item.get" in res.updated_content


def test_replay_tolerance():
    already_applied = """def print_receipt(total: float) -> None:
    print(f"Updated Total: ${total:.2f}")"""
    current = SAMPLE_PYTHON_FILE.replace("Receipt Total", "Updated Total")
    res = perform_file_surgery(
        current,
        'def print_receipt(total: float) -> None:\n    print(f"Receipt Total: ${total:.2f}")',
        already_applied,
        "calc.py",
    )
    assert res.status == "replay"
    assert res.updated_content == current


def test_multiple_matches_rejected():
    content = "alpha = 1\nbeta = 2\nalpha = 1\n"
    res = perform_file_surgery(content, "alpha = 1\n", "alpha = 10\n", "test.py")
    assert res.status == "multiple_matches"
    assert res.error_message is not None
    assert "not unique" in res.error_message


def test_not_found_produces_context_hint():
    res = perform_file_surgery(
        SAMPLE_PYTHON_FILE, "def missing_function(): pass", "pass", "calc.py"
    )
    assert res.status == "not_found"
    assert res.error_message is not None
    assert "Closest matching section in calc.py" in res.error_message
    assert res.context_hint is not None
