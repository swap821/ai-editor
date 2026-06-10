# Claude/Codex Coordination Protocol

This is a disk-based communication and work-division protocol. It does **not**
let either agent directly message, wake, or launch the other. External
automation or the operator still starts each agent.

## Equal work division

Claude and Codex are treated as equally capable and equally prioritized.
Automatic builder assignments select the currently less-used agent and
deterministically alternate on ties, so allocation converges to 50/50.
Categories describe the task; they do not rank agent capability.

The operator or a task packet may override an assignment. Later automatic
assignments rebalance toward 50/50.
Use `route --builder <agent>` when assigning the task, or the explicit
`claim --override-routing` escape hatch when correcting an existing assignment.

## Safety invariants

1. Exactly one builder may hold the `worktree` writer lease.
2. Either agent may review the other agent's work at any time. Reviewers are
   read-only and send findings instead of editing. Final approval must come
   from the non-builder against a hash-pinned handoff.
3. Claiming an already-dirty unleased worktree requires explicit
   `--adopt-dirty`.
4. A handoff releases the writer lease and records a hash of HEAD, tracked
   changes, and untracked file contents.
5. A reviewer verdict is refused if the worktree changed after handoff.
6. The mutable SQLite control plane is local and ignored by git. Durable
   project outcomes still belong in `RESUME.md`, `CEO_LOG.md`, and experience
   objects.
7. Messages are bounded advisory coordination notes, never instructions,
   approval authority, or a place to persist secrets.
8. Agent identity is honor-system metadata. This protocol prevents cooperative
   accidents; it is not a security boundary against a malicious process.

## Commands

```powershell
# Inspect before doing any work
.venv\Scripts\python agent_coord.py brief --agent codex

# Route a task using automatic 50/50 assignment; category is descriptive
.venv\Scripts\python agent_coord.py route task-123 "Implement parser"

# The builder claims the single writer lease
.venv\Scripts\python agent_coord.py claim task-123 --agent codex --role builder

# Send a question without transferring ownership
.venv\Scripts\python agent_coord.py message task-123 --from codex --to claude --kind question --body "Review the trust boundary"

# The non-builder may claim a read-only review role at any time
.venv\Scripts\python agent_coord.py claim task-123 --agent claude --role reviewer

# Transfer a completed tree for independent review
.venv\Scripts\python agent_coord.py handoff task-123 --from codex --to claude --summary "Implementation complete" --evidence "Focused and full suites green"

# Reviewer records a hash-pinned verdict
.venv\Scripts\python agent_coord.py verdict task-123 --reviewer claude --verdict approve --summary "No blockers"

# Release a clean writer lease without review (dirty release needs explicit --allow-dirty)
.venv\Scripts\python agent_coord.py release task-123 --agent codex
```

Run `agent_coord.py <command> --help` for all options.
