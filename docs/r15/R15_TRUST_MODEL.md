# R15 Trust Model

## Philosophy
The system defaults to zero-trust for all generative output. The AI is the engine, but the boundary logic is deterministic, compiled, and unalterable by the AI itself.

## Core Tenets
1. **Human Sovereign Authority**: Only the human operator can approve destructive changes, system configuration shifts, and budget limits.
2. **Fail-Closed Sandboxing**: All experimental generation (maintenance, feature development) occurs in isolated `tempfile` spaces or constrained Git worktrees.
3. **Immutable Auditing**: All trajectory steps, decisions, and outcomes are permanently logged to `aios/memory/experiences.jsonl`. No model can rewrite history.
4. **Deterministic Validation**: A fix is not considered "working" based on a model's assertion. It is only considered working if the deterministic scanner returns a 0 exit code.
