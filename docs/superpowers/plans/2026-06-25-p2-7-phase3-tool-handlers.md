# P2-7 Phase 3 — Extract ToolAgent dispatch handlers

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the large tool-action handlers out of `aios/agents/tool_agent.py` into focused module(s), leaving `ToolAgent.run()` as the pure orchestrator and keeping the existing event/security contract unchanged.

**Architecture:** Create a new `aios/agents/tool_handlers.py` module containing pure handler callables for each tool (`read_file`, `read_directory`, `execute_terminal`, `edit_file`, `create_file`, `verify`, `browse`, `plan`, `self_analyze`, `propose_fixes`). Each handler receives the dependencies it needs as parameters instead of accessing `self`. `ToolAgent._dispatch` becomes a thin router that passes `self` attributes into the handlers. Helper functions private to a single handler (`_format_exec_result`, `_normalise_sandbox_paths`) move with their handlers. `_auto_verify` and `_pre_apply_grants` are orchestration helpers that stay in `ToolAgent` for now because they yield events and coordinate multiple handlers.

**Tech Stack:** Python 3.12, FastAPI/uvicorn, pytest.

---

## File structure

- **Create:** `aios/agents/tool_handlers.py` — all tool-action handler functions and their private helpers.
- **Modify:** `aios/agents/tool_agent.py` — reduce `_dispatch`, `_execute`, `_verify`, `_read_file`, `_read_directory`, `_edit_file`, `_create_file`, `_browse`, `_plan`, `_self_analyze`, `_propose_fixes` to thin wrappers; remove duplicated module-level helpers if they move.
- **Test:** `tests/test_tool_agent.py` (existing regression suite, must still pass without edits).

---

### Task 1: Move read-only file-system handlers

**Files:**
- Create: `aios/agents/tool_handlers.py`
- Modify: `aios/agents/tool_agent.py:1066-1091` and imports

- [ ] **Step 1: Create handler module skeleton**

Create `aios/agents/tool_handlers.py`:

```python
"""Tool-action handlers for ToolAgent.

Each handler is a stateless callable that receives the dependencies it needs
from ToolAgent and returns the same (output, status, failed) tuple.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def read_file(
    filepath: str,
    *,
    read_root: Path,
    file_read_limit: int,
) -> tuple[str, str, bool]:
    """Read a scoped text file, redact secrets, and return its contents."""
    ...


def read_directory(
    path: str,
    *,
    read_root: Path,
) -> tuple[str, str, bool]:
    """List the contents of a scoped directory."""
    ...
```

- [ ] **Step 2: Move `_read_file` and `_read_directory` bodies**

Copy the bodies of `ToolAgent._read_file` and `ToolAgent._read_directory` (lines ~1066-1091) into `read_file` and `read_directory`. Replace `self.read_root` with the `read_root` parameter. Import `_resolve_within` and `scan_and_redact` from `aios.agents.tool_agent` (or move them into `tool_handlers.py` if they are module-level and only used by handlers).

- [ ] **Step 3: Replace ToolAgent handlers with wrappers**

In `aios/agents/tool_agent.py`:

```python
from aios.agents import tool_handlers

# ...

    def _read_file(self, filepath: str) -> tuple[str, str, bool]:
        return tool_handlers.read_file(
            filepath,
            read_root=self.read_root,
            file_read_limit=_FILE_READ_LIMIT,
        )

    def _read_directory(self, path: str) -> tuple[str, str, bool]:
        return tool_handlers.read_directory(path, read_root=self.read_root)
```

- [ ] **Step 4: Run focused tests**

Run: `.venv/Scripts/python -m pytest tests/test_tool_agent.py -q`
Expected: all 74 tests pass.

- [ ] **Step 5: Commit**

```bash
git add aios/agents/tool_handlers.py aios/agents/tool_agent.py
git commit -m "P2-7 Phase 3a — extract read_file/read_directory handlers"
```

---

### Task 2: Move write handlers (`edit_file`, `create_file`)

**Files:**
- Modify: `aios/agents/tool_handlers.py`, `aios/agents/tool_agent.py:1093-1305`

- [ ] **Step 1: Add write handlers to `tool_handlers.py`**

Add `edit_file` and `create_file` functions. Signatures (exact names/types may mirror existing code):

```python
def edit_file(
    filepath: str,
    old_string: str,
    new_string: str,
    *,
    read_root: Path,
    approved_edits: dict[str, tuple[str, str]],
    snapshot: Any,
    audit: Any,
) -> tuple[str, str, bool]:
    ...


def create_file(
    filepath: str,
    content: str,
    *,
    read_root: Path,
    approved_creations: dict[str, str],
    snapshot: Any,
    audit: Any,
) -> tuple[str, str, bool]:
    ...
```

- [ ] **Step 2: Move bodies and private helpers**

Move the bodies of `ToolAgent._edit_file` and `ToolAgent._create_file` into the new functions. Move/import `_atomic_write_text`, `scan_and_redact`, `scope_lock.is_path_in_scope`, `scope_lock.get_scope_roots`, and `Zone.YELLOW` as needed. Replace `self.read_root`, `self.approved_edits`, `self.approved_creations`, `self.snapshot`, and `self._audit` with the parameters.

- [ ] **Step 3: Replace ToolAgent handlers with wrappers**

```python
    def _edit_file(self, filepath: str, old_string: str, new_string: str) -> tuple[str, str, bool]:
        return tool_handlers.edit_file(
            filepath,
            old_string,
            new_string,
            read_root=self.read_root,
            approved_edits=self.approved_edits,
            snapshot=self.snapshot,
            audit=self._audit,
        )

    def _create_file(self, filepath: str, content: str) -> tuple[str, str, bool]:
        return tool_handlers.create_file(
            filepath,
            content,
            read_root=self.read_root,
            approved_creations=self.approved_creations,
            snapshot=self.snapshot,
            audit=self._audit,
        )
```

- [ ] **Step 4: Run focused tests**

Run: `.venv/Scripts/python -m pytest tests/test_tool_agent.py -q`
Expected: all 74 tests pass.

- [ ] **Step 5: Commit**

```bash
git add aios/agents/tool_handlers.py aios/agents/tool_agent.py
git commit -m "P2-7 Phase 3b — extract edit_file/create_file handlers"
```

---

### Task 3: Move execution, verification, browse, plan, and analysis handlers

**Files:**
- Modify: `aios/agents/tool_handlers.py`, `aios/agents/tool_agent.py:1329-1556`

- [ ] **Step 1: Add remaining handlers to `tool_handlers.py`**

Add functions:

```python
def execute_terminal(
    command: str,
    *,
    approved_commands: set[str],
    executor: Any,
    session_id: Optional[str],
) -> tuple[str, str, bool]:
    ...


def verify_command(
    command: str,
    *,
    approved: bool,
    approved_commands: set[str],
    verifier: Any,
    session_id: Optional[str],
) -> tuple[str, str, bool]:
    ...


def browse_url(
    url: str,
    *,
    approved_commands: set[str],
) -> tuple[str, str, bool]:
    ...


def plan_task(
    directive: str,
    *,
    planner: Any,
) -> tuple[str, str, bool]:
    ...


def self_analyze(
    target: str,
    *,
    read_root: Path,
) -> tuple[str, str, bool]:
    ...


def propose_fixes(
    analysis: str,
    *,
    read_root: Path,
    self_analysis_llm: Any,
) -> tuple[str, str, bool]:
    ...
```

- [ ] **Step 2: Move bodies and private helpers**

Move `ToolAgent._execute`, `_verify`, `_browse`, `_plan`, `_self_analyze`, `_propose_fixes` bodies into the new functions. Move private helpers `_format_exec_result` and `_normalise_sandbox_paths` into `tool_handlers.py` with their handlers. Replace `self.*` accesses with parameters. For `_verify`, keep the `REQUIRE_APPROVAL`/`BLOCKED` branches and delegate pass/fail formatting to `tool_loop_helpers.format_verifier_result`.

- [ ] **Step 3: Replace ToolAgent handlers with wrappers**

Update `ToolAgent._execute`, `_verify`, `_browse`, `_plan`, `_self_analyze`, `_propose_fixes` to delegate to the new handlers, passing the required `self` attributes.

- [ ] **Step 4: Run focused tests**

Run: `.venv/Scripts/python -m pytest tests/test_tool_agent.py -q`
Expected: all 74 tests pass.

- [ ] **Step 5: Commit**

```bash
git add aios/agents/tool_handlers.py aios/agents/tool_agent.py
git commit -m "P2-7 Phase 3c — extract execute/verify/browse/plan/self-analyze handlers"
```

---

### Task 4: Final cleanup, full-suite verification, and doc update

**Files:**
- Modify: `aios/agents/tool_agent.py`, `.aios/state/RESUME.md`, `.aios/memory/experiences.jsonl`

- [ ] **Step 1: Clean up imports and dead code**

Remove any imports from `aios/agents/tool_agent.py` that are now only used by handlers (e.g., `requests`, `BeautifulSoup`, `socket`, `ipaddress`, `urllib.parse`, `SelfAnalysisAgent`, `PlannerError`, etc.) and move them to `aios/agents/tool_handlers.py`. Ensure `tool_agent.py` still imports only what `run()`, `_dispatch`, `_auto_verify`, `_pre_apply_grants`, and the thin wrappers need.

- [ ] **Step 2: Run full backend suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: `666 passed, 1 skipped`.

- [ ] **Step 3: Update RESUME.md**

Add a "P2-7 Phase 3 — ToolAgent dispatch handlers" section under Completed, summarizing the extraction, test counts, and commit SHA.

- [ ] **Step 4: Append Experience Object**

Append a JSON line to `.aios/memory/experiences.jsonl` describing the refactor, any failure modes, and lessons.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "P2-7 Phase 3 — extract ToolAgent dispatch handlers" -m "- Move read_file, read_directory, edit_file, create_file, execute_terminal, verify, browse, plan, self_analyze, propose_fixes into aios/agents/tool_handlers.py" -m "- Leave ToolAgent.run() as orchestrator; frozen security core untouched" -m "- Verified: tests/test_tool_agent.py 74 passed; full backend suite 666 passed, 1 skipped"
```

---

## Self-review

1. **Spec coverage:** Every tool handler listed in the Phase 3 goal (`_read_file`, `_read_directory`, `_edit_file`, `_create_file`, `_execute`, `_browse`, `_plan`, `_self_analyze`, `_propose_fixes`, `_verify`) has a task that moves it. `_auto_verify` and `_pre_apply_grants` are intentionally kept as orchestration because they yield events and coordinate handlers.
2. **Placeholder scan:** No TBD/TODO/filler. Code blocks show real signatures and wrapper snippets.
3. **Type consistency:** Handler signatures use the same parameter names as the `ToolAgent` attributes they replace (`read_root`, `approved_edits`, `approved_creations`, `snapshot`, `audit`, `executor`, `verifier`, `planner`, `self_analysis_llm`).
