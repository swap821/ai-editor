"""Resilient AST and fuzzy file surgery engine for GAGOS (Wave 1, Pillar 2).

Solves the local 7B model fragility problem where exact-string matching in
`edit_file` causes high failure rates due to minor whitespace, indentation,
quote, or formatting drift.

Provides a deterministic 4-tier waterfall:
  Tier 1: Exact byte/substring match (fast path)
  Tier 2: Whitespace-normalized line-sequence match (ignores indent/line-ending drift)
  Tier 3: Line-bounded high-confidence fuzzy match (difflib SequenceMatcher >= 0.92)
  Tier 4: Python AST node replacement (replaces target def/class by AST boundary)

Fail-closed: if an unambiguous match cannot be proven, surgery fails cleanly and
emits an exact context-window hint extracted from the file at the closest position.
"""

from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class SurgeryResult:
    """Outcome of an edit surgery attempt."""

    status: str  # 'exact' | 'normalized' | 'fuzzy' | 'ast' | 'replay' | 'not_found' | 'multiple_matches' | 'error'
    updated_content: Optional[str] = None
    matched_target: Optional[str] = None
    error_message: Optional[str] = None
    similarity: float = 1.0
    tier: int = 1
    context_hint: Optional[str] = None


def _normalize_line(line: str) -> str:
    """Collapse internal whitespace and strip leading/trailing spaces and newlines."""
    return " ".join(line.strip().split())


def _find_closest_context_window(
    current_lines: list[str],
    old_lines: list[str],
    window_padding: int = 3,
) -> tuple[int, int, str]:
    """Locate the most similar section of current_lines to old_lines and return (start, end, text)."""
    if not current_lines:
        return 0, 0, ""

    norm_target = " ".join(_normalize_line(line) for line in old_lines if _normalize_line(line))
    if not norm_target:
        return 0, min(len(current_lines), 10), "".join(current_lines[:10])

    best_ratio = 0.0
    best_idx = 0
    window_size = max(1, len(old_lines))

    for i in range(len(current_lines)):
        chunk = current_lines[i : i + window_size]
        norm_chunk = " ".join(_normalize_line(l) for l in chunk if _normalize_line(l))
        ratio = difflib.SequenceMatcher(None, norm_target, norm_chunk).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = i

    start = max(0, best_idx - window_padding)
    end = min(len(current_lines), best_idx + window_size + window_padding)
    context_text = "".join(
        f"{idx + 1:4d} | {current_lines[idx]}" for idx in range(start, end)
    )
    return start + 1, end, context_text


def _match_tier_2_normalized(
    current_lines: list[str],
    old_lines: list[str],
) -> list[tuple[int, int]]:
    """Return all [start, end) line ranges in current_lines matching normalized old_lines."""
    if not old_lines or not current_lines:
        return []

    norm_old = [_normalize_line(l) for l in old_lines]
    # Filter out empty leading/trailing lines for more resilient boundary alignment
    lead_trim = 0
    while lead_trim < len(norm_old) and not norm_old[lead_trim]:
        lead_trim += 1
    trail_trim = len(norm_old)
    while trail_trim > lead_trim and not norm_old[trail_trim - 1]:
        trail_trim -= 1

    active_norm_old = norm_old[lead_trim:trail_trim]
    if not active_norm_old:
        return []

    window_len = len(active_norm_old)
    matches: list[tuple[int, int]] = []

    for i in range(len(current_lines) - window_len + 1):
        window = current_lines[i : i + window_len]
        if [_normalize_line(l) for l in window] == active_norm_old:
            matches.append((i, i + window_len))

    return matches


def _match_tier_3_fuzzy(
    current_lines: list[str],
    old_lines: list[str],
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    min_similarity: float = 0.92,
) -> tuple[Optional[tuple[int, int]], float]:
    """Return the unique (start, end) line range matching old_lines with difflib ratio >= min_similarity."""
    if not current_lines or not old_lines:
        return None, 0.0

    target_str = "".join(old_lines)
    window_base = len(old_lines)

    # Apply search boundaries if given (convert 1-indexed to 0-indexed)
    line_min = 0
    line_max = len(current_lines)
    if start_line is not None and start_line > 0:
        line_min = max(0, start_line - 1 - 5)
    if end_line is not None and end_line > 0:
        line_max = min(len(current_lines), end_line + 5)

    def _overlaps(r1: tuple[int, int], r2: tuple[int, int]) -> bool:
        return not (r1[1] <= r2[0] or r2[1] <= r1[0])

    candidate_sizes = [
        s for s in (window_base - 1, window_base, window_base + 1) if s > 0
    ]

    best_match: Optional[tuple[int, int]] = None
    best_ratio = 0.0
    second_ratio = 0.0

    # First pass: find the best match across all positions and window sizes
    for size in candidate_sizes:
        for i in range(line_min, min(line_max, len(current_lines) - size + 1)):
            candidate_str = "".join(current_lines[i : i + size])
            ratio = difflib.SequenceMatcher(
                None, target_str.rstrip(), candidate_str.rstrip()
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = (i, i + size)

    if best_match is None or best_ratio < min_similarity:
        return None, best_ratio

    # Second pass: find the highest ratio at a NON-OVERLAPPING position
    for size in candidate_sizes:
        for i in range(line_min, min(line_max, len(current_lines) - size + 1)):
            cand = (i, i + size)
            if _overlaps(best_match, cand):
                continue
            candidate_str = "".join(current_lines[i : i + size])
            ratio = difflib.SequenceMatcher(
                None, target_str.rstrip(), candidate_str.rstrip()
            ).ratio()
            if ratio > second_ratio:
                second_ratio = ratio

    # Require unambiguous separation from any non-overlapping candidate
    if second_ratio < 0.70 or (best_ratio - second_ratio) >= 0.08:
        return best_match, best_ratio

    return None, best_ratio


def _match_tier_4_ast(
    current_content: str,
    old_string: str,
    filepath: str,
) -> Optional[tuple[str, float]]:
    """Return matching source segment from current_content if old_string targets a Python definition."""
    if not filepath.endswith(".py"):
        return None

    try:
        old_tree = ast.parse(old_string)
        curr_tree = ast.parse(current_content)
    except SyntaxError:
        return None

    # Check if old_string is a single top-level FunctionDef, AsyncFunctionDef, or ClassDef
    target_nodes = [
        node
        for node in old_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    if len(target_nodes) != 1 or len(old_tree.body) != 1:
        return None

    target_node = target_nodes[0]
    target_name = target_node.name

    # Locate candidate in current file AST
    matching_nodes = [
        node
        for node in ast.walk(curr_tree)
        if isinstance(node, type(target_node)) and getattr(node, "name", None) == target_name
    ]

    if len(matching_nodes) != 1:
        return None

    match_node = matching_nodes[0]
    matched_segment = ast.get_source_segment(current_content, match_node)
    if matched_segment:
        return matched_segment, 0.95

    return None


def perform_file_surgery(
    current_content: str,
    old_string: str,
    new_string: str,
    filepath: str = "",
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> SurgeryResult:
    """Execute multi-tier file surgery to apply an edit robustly.

    Follows a 4-tier deterministic resolution:
      1. Exact byte match
      2. Normalized line-sequence match
      3. High-confidence fuzzy sequence match (>= 0.92 similarity)
      4. AST node replacement (Python only)

    Returns a SurgeryResult detailing status, updated content, tier, and context hints.
    """
    if not old_string:
        return SurgeryResult(
            status="error",
            error_message="old_string must be non-empty.",
            similarity=0.0,
            tier=0,
        )

    # Replay tolerance
    if new_string and new_string in current_content and old_string not in current_content:
        return SurgeryResult(
            status="replay",
            updated_content=current_content,
            matched_target=new_string,
            similarity=1.0,
            tier=1,
        )

    # Tier 1: Exact Substring Match
    occurrences = current_content.count(old_string)
    if occurrences == 1:
        updated = current_content.replace(old_string, new_string, 1)
        return SurgeryResult(
            status="exact",
            updated_content=updated,
            matched_target=old_string,
            similarity=1.0,
            tier=1,
        )
    if occurrences > 1:
        return SurgeryResult(
            status="multiple_matches",
            error_message=(
                f"old_string is not unique in {filepath or 'file'} "
                f"({occurrences} matches); add surrounding context."
            ),
            similarity=1.0,
            tier=1,
        )

    current_lines = current_content.splitlines(keepends=True)
    old_lines = old_string.splitlines(keepends=True)

    # Tier 2: Normalized Line-Sequence Match
    norm_matches = _match_tier_2_normalized(current_lines, old_lines)
    if len(norm_matches) == 1:
        start_idx, end_idx = norm_matches[0]
        matched_target = "".join(current_lines[start_idx:end_idx])
        # Replace the matched slice in current_content
        updated = current_content.replace(matched_target, new_string, 1)
        return SurgeryResult(
            status="normalized",
            updated_content=updated,
            matched_target=matched_target,
            similarity=0.99,
            tier=2,
        )
    if len(norm_matches) > 1:
        return SurgeryResult(
            status="multiple_matches",
            error_message=(
                f"Normalized old_string matches multiple locations in {filepath or 'file'} "
                f"({len(norm_matches)} matches); add surrounding context."
            ),
            similarity=0.99,
            tier=2,
        )

    # Tier 3: Line-Bounded / High-Confidence Fuzzy Match
    fuzzy_match, ratio = _match_tier_3_fuzzy(
        current_lines,
        old_lines,
        start_line=start_line,
        end_line=end_line,
        min_similarity=0.92,
    )
    if fuzzy_match is not None:
        start_idx, end_idx = fuzzy_match
        matched_target = "".join(current_lines[start_idx:end_idx])
        updated = current_content.replace(matched_target, new_string, 1)
        return SurgeryResult(
            status="fuzzy",
            updated_content=updated,
            matched_target=matched_target,
            similarity=ratio,
            tier=3,
        )

    # Tier 4: AST Node Replacement (Python files)
    ast_match = _match_tier_4_ast(current_content, old_string, filepath)
    if ast_match is not None:
        matched_target, ast_sim = ast_match
        updated = current_content.replace(matched_target, new_string, 1)
        return SurgeryResult(
            status="ast",
            updated_content=updated,
            matched_target=matched_target,
            similarity=ast_sim,
            tier=4,
        )

    # All tiers failed: compute closest context hint
    hint_start, hint_end, context_text = _find_closest_context_window(
        current_lines, old_lines, window_padding=4
    )
    hint_msg = (
        f"[ERROR] old_string not found in {filepath or 'file'}. It must match the file "
        "byte-for-byte, including indentation -- do not retype it from memory.\n"
        f"Closest matching section in {filepath or 'file'} (lines {hint_start}-{hint_end}):\n"
        f"--------------------------------------------------\n"
        f"{context_text}"
        f"--------------------------------------------------\n"
        "Either read_file and copy an exact snippet from above, or call "
        f"overwrite_file with the COMPLETE new body of {filepath or 'file'}, which needs no snippet match."
    )

    return SurgeryResult(
        status="not_found",
        error_message=hint_msg,
        similarity=ratio,
        tier=0,
        context_hint=context_text,
    )
