"""Candidate 3 — backend code_chunk streaming.

The LLM is non-streaming (function calling), so the COMPLETE code is chunked at
emit time into a growing sequence of snapshots, and finish_stream yields code_chunk
events (incremental reveal) before the final code event. Honest: this is
emit-time chunking, not raw model tokens.
"""
from __future__ import annotations

import re

from aios.agents.tool_loop_helpers import chunk_code, finish_stream

_FENCE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)


def test_chunk_code_grows_to_the_full_code() -> None:
    code = "\n".join(f"line {i}" for i in range(1, 21))
    snaps = chunk_code(code)
    assert snaps, "expected at least one snapshot"
    # strictly growing-ish: each snapshot is a prefix of the full code
    for s in snaps:
        assert code.startswith(s)
    assert snaps[-1] == code  # the last snapshot is the whole thing


def test_chunk_code_single_line_is_one_snapshot() -> None:
    assert chunk_code("print('hi')") == ["print('hi')"]
    assert chunk_code("") == []


def test_finish_stream_emits_code_chunks_before_code() -> None:
    answer = "Here it is:\n```python\n" + "\n".join(f"x{i} = {i}" for i in range(1, 12)) + "\n```"
    events = list(finish_stream(answer, code_fence=_FENCE, preview_limit=500))
    kinds = [e["type"] for e in events]
    assert "code_chunk" in kinds
    assert "code" in kinds
    # code_chunks come before the final code event...
    assert kinds.index("code_chunk") < kinds.index("code")
    # ...and the final code event carries the full block.
    code_event = next(e for e in events if e["type"] == "code")
    last_chunk = [e for e in events if e["type"] == "code_chunk"][-1]
    assert last_chunk["code"] == code_event["code"]
