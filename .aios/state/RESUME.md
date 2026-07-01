# RESUME MANIFEST

Last updated: 2026-07-01T13:17Z

## Current Goal
Execute the fusion roadmap slice-by-slice without premature birth claims, under
one-writer discipline. Kimi is unavailable; Codex is the solo active builder for
this combined K/C pass.

## Last Completed + Verified
- Fusion C1 is already landed on origin/master at 53e8c74; GitHub CI run
  28516331659 passed.
- Local combined pass completed for K1-K4 plus C2-C4:
  - K1: removed unused httpx2/httpcore2/truststore pins and wrote
    docs/superpowers/specs/2026-07-01-import-graph.md with dependency triage
    plus AST import graph evidence.
  - K2/C4: added Bedrock/Gemini stream_chat, failover streaming, and real
    no-tool /api/v1/chat chunk consumption with truthful lazy route metadata.
  - K3: hardened cloud privacy filtering with configurable coding history window
    and bounded large-blob truncation instead of all-or-nothing redaction.
  - K4: precompiled model-selector regex hints and capped recursive facts CTE
    traversal at 256 rows.
  - C2/C3: default /api/generate now pauses on low calibrated alignment
    confidence before tool loops; verified lessons/development/skill evidence
    calibrates the confidence gate with SSE evidence.

## Verification
- Focused slice suite passed: 102 tests across Bedrock, Gemini, privacy filter,
  model selector, facts, failover, chat streaming, confidence gating, and events.
- Full backend CI-equivalent gate passed:
  .venv\Scripts\python.exe -m pytest -q --cov=aios --cov-report=term-missing --cov-report=xml --cov-fail-under=85
  => coverage 88.85%, 4 skips.
- .venv\Scripts\python.exe -m compileall -q aios tests passed.
- git diff --check passed (only CRLF conversion warnings).
- C3 calibration overhead probe: empty_avg_ms=0.0033, lesson_avg_ms=0.0037.

## Single Next Action
Operator landing decision: review this combined local diff, then explicitly say
whether to commit/push K1-K4+C2-C4 as one roadmap commit. Do not declare born.

## Open Approvals / Blockers
- Not committed or pushed yet in this closeout.
- Frozen security spine was not touched: no changes under aios/security/*.
- Existing untracked tool/skill artifacts remain unrelated: .agents/skills/,
  .codex/, 500, .aios/state/CODEX_KEEPERS_HANDOFF.md,
  .aios/state/RUFLO_MEMORY_MIGRATION_TASK.md, and tuple[list[str].
- New untracked file from this pass: docs/superpowers/specs/2026-07-01-import-graph.md.

## Active Files
- requirements.txt
- aios/api/main.py
- aios/config.py
- aios/core/bedrock.py
- aios/core/events.py
- aios/core/failover.py
- aios/core/gemini.py
- aios/core/model_selector.py
- aios/core/privacy_filter.py
- aios/memory/facts.py
- tests/test_api.py
- tests/test_bedrock.py
- tests/test_chat.py
- tests/test_facts.py
- tests/test_failover.py
- tests/test_gemini.py
- tests/test_privacy_filter.py
- docs/superpowers/specs/2026-07-01-import-graph.md
- .aios/state/RESUME.md, .aios/memory/experiences.jsonl

## Notes Not Yet Promoted
- /api/generate remains non-streaming for tool-capable cloud turns because
  streamed provider deltas do not safely carry tool calls. Real streaming is now
  consumed on no-tool chat paths.
- Failover stream only changes provider before the first chunk; after any chunk
  is emitted, later provider errors surface instead of mixing model outputs.