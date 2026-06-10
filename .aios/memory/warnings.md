# Exploded Warnings

_Patterns that harmed >= 2x get promoted here, loudest at the top._

## ONE WRITER PER WORKTREE

Do not infer ownership from an agent UI's "working" badge or from a stale
`RESUME.md`. Concurrent Claude/Codex writes caused stale handoffs, post-commit
dirty trees, and duplicated closeout work. Before edits, use
`python agent_coord.py brief --agent <name>` and hold the active `worktree`
builder lease. Reviewers remain read-only; transfer ownership only through a
hash-pinned handoff.
