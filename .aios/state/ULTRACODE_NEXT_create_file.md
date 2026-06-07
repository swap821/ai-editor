# ULTRACODE TASK (QUEUED) — `create_file` tool

> **Sequencing:** start this **only after task (a) (`ULTRACODE_TASK.md`) is merged.**
> Both touch `aios/agents/tool_agent.py`; rebase this branch onto `origin/master`
> after (a) lands so the PR diff is clean. One focused PR.
> Claude Code (local) reviews on evidence + merges (the #1–#4 loop).

---

## TASK — add a gated `create_file` tool so the agent can author NEW files in its sandbox

**Why:** today the agent can *modify* existing files (`edit_file`, search/replace) but
**cannot create a new one** — `edit_file` requires a non-empty `old_string` that must already
exist. That blocks the agent from authoring new tests/modules even inside its sandbox, which is
the capability that turns the "first breath" into a sustainable "rhythm." `create_file` adds that,
behind the SAME human gate.

**Non-negotiable safety (mirror `edit_file` exactly — do NOT invent a new security path):**
- **Scope-locked** to `config.SCOPE_ROOTS` (the `training_ground/` sandbox) via the SAME check
  `edit_file` uses (`is_path_in_scope` on the path resolved under `read_root`). A path outside
  scope **auto-escalates to RED → refused** (RED is hard-blocked here even after approval). A `../`
  / absolute / symlink escape is refused.
- **YELLOW + paused for approval**, exactly like `edit_file`: the turn pauses with a
  `human_required` event carrying a **preview** of the new file (path + full content), and resumes
  only when the frontend re-sends with the approved creation.
- **Audit before write, fail-closed on snapshot AND audit** (copy `_edit_file`'s ordering at
  `tool_agent.py:613`): take a pre-create snapshot (the RollbackEngine snapshots the sandbox
  work-tree; "before" = file absent, so rollback deletes it — correct), `log_action` the create,
  THEN write. If snapshot or audit fails, do not write.
- **Refuse if the file already exists** → return an error telling the model to use `edit_file`
  instead. `create_file` is for new paths only.
- **Read-only/GREEN tools unaffected.** Do not touch `aios/security/` (frozen core).

### Files & changes (copy the `edit_file` pattern throughout)

**1. `aios/agents/tool_agent.py`**
- `TOOL_SPECS`: add a `create_file` entry with required params `filepath` (string, project-relative,
  must be inside the sandbox) and `content` (string, the full file body). Description: creates a NEW
  file; caution-level (paused for approval); never overwrites an existing file. Add it to the
  module-docstring tool list too.
- `_dispatch`: route `create_file` → `_create_file(filepath, content)`.
- **Approval plumbing:** mirror `approvedEdits` with an `approvedCreations` channel — a dict keyed by
  `filepath` → approved `content` (see how `approvedEdits` is threaded through `__init__`/`run`/the
  resume path; replicate it). On a paused create, record no answer (so the resend replays the same
  turn), and on resume apply the approved creation **by filepath** (robust to a local model
  regenerating drifted `content` on resume — same lesson as `edit_file`).
- `_create_file(filepath, content)`:
  1. `resolved = _resolve_within(self.read_root, filepath)`; `None` → blocked ("escapes the project
     root").
  2. `is_path_in_scope(str(resolved))` must hold; otherwise blocked/RED (out-of-sandbox writes are
     refused) — reuse the exact zone handling `edit_file` uses.
  3. If `resolved.exists()` → error ("file already exists; use edit_file").
  4. If not yet approved → pause: emit the `human_required` event with a preview payload
     (`{tool: "create_file", filepath, content}`); the diff the UI shows is `content` rendered as an
     all-additions diff (DiffView against empty string).
  5. On approval → snapshot (fail-closed) → `log_action` (fail-closed) → create parent dirs if
     needed **only within scope** → write the file. Return an `ok` tool_result summarizing
     (path + bytes/lines written).

**2. `aios/api/main.py` (`/api/generate`)**
- Accept `approvedCreations` in the request body (parallel to `approvedEdits`) and pass it into
  `ToolAgent`. No new endpoint.

**3. `frontend/src/`**
- `App.jsx`: add `approvedCreations` state + the approve/reject/resume wiring, mirroring
  `approvedEdits` (`handleApproveAction`/`handleRejectAction`/`streamGenerate`). The per-request
  whitelist boundary stays the same (reset on each new user message; grow only across an
  approve→resume chain).
- The approval bar: render a "new file" preview by reusing `DiffView` (diff of `""` → `content`,
  which shows all-additions). Add a `create_file` entry to `MessageBubble.jsx` `TOOL_META`
  (e.g. ✏️/🆕 "Create file").

### Tests
- `tests/test_tool_agent.py` (mirror the `edit_file` tests):
  - create a new in-sandbox file → first run PAUSES (`human_required`, file NOT yet written); after
    resend with `approvedCreations` → file exists with exact content + a pre-create snapshot recorded.
  - `create_file` on an **existing** path → error (not written), message points to `edit_file`.
  - `create_file` **out of scope** (e.g. `aios/x.py`) → blocked/RED, file not created.
  - `create_file` with a `../` escape → blocked.
  - **fail-closed on audit failure** → file not written.
- Frontend (`vitest`): `DiffView` renders new-file content as additions (one test).

### Acceptance
- Full `pytest -q` green. **Cloud (Linux) note:** the 2 pre-existing environmental `test_security.py`
  failures (Windows `C:\…` path + a random `/tmp/pytest-…` entropy hit) are NOT yours — confirm
  identical with your changes stashed; do not "fix" them. Windows baseline 171/1 (+ (a)'s tests +
  these). Frontend `eslint` + `vitest` + `vite build` green.
- `aios/security/` untouched. One focused PR. Title: `Agent: gated create_file tool (author new files in the sandbox)`.
