# RESUME MANIFEST

Last updated: 2026-07-09T11:26:03+05:30 by Codex.
Task: `v10-vulture-complete-replacement` / Phase 2 vulture hardening follow-up.

## Current Goal
Integrate the uploaded GAGOS v10 plan and scaffold as an architectural
contract, not production code, while preserving the proven v7/v8 safety,
council, worker, memory, router, verifier, hibernation, resource, and UI spine.

## Last Completed + Verified Step
The operator's prepared `vulture_sanitation_COMPLETE.py` was safety-reviewed and
partially integrated as a read-only hardening slice. Unsafe scaffold behaviors
were intentionally not copied:

- rejected autonomous quarantine storage, SQLite ledger writes, purge/restore,
  pheromone inversion, subprocess test loops, and file unlink/write paths;
- kept the existing local-only proposal/evidence contract;
- added cognitive-parasite detection for anti-immune-system language;
- added `scan_code_paths()` / `scan_vulture_code_paths()` as AST-only dead-import
  evidence, without edits, test execution, quarantine, cloud, or mutation;
- added tests proving the new detections and the absence of write/purge/subprocess
  organs.

Local verification:

- Red-first:
  `.venv\Scripts\python.exe -m pytest tests\test_vulture_sanitation.py -q`
  failed on missing `cognitive_parasite` and missing `scan_code_paths`.
- `.venv\Scripts\python.exe -m pytest tests\test_vulture_sanitation.py -q`
  -> 7 passed.
- `.venv\Scripts\python.exe -m pytest tests\test_vulture_sanitation.py tests\test_thesis_audit.py tests\test_security.py tests\test_hibernation_resource.py tests\test_dead_code_hygiene.py tests\test_constitution.py tests\adversarial\test_api_security.py -q`
  -> 129 passed, 2 skipped.
- `.venv\Scripts\python.exe -m pytest -q` -> exit 0, 4 skipped, total coverage
  92%.

## Single Next Action
Review and, if accepted, commit the vulture hardening follow-up; then resume
Phase 4 as the next scoped roadmap task: signal ganglia and council memory as
typed adapters/evidence around the existing council call chain.

## Open Approvals / Blockers
- No frozen-core files were edited in Phase 3.
- Any future ecosystem promotion under `aios/security/*` still requires explicit
  Section VIII approval.
- Existing untracked workspace noise and older stashes remain intentionally
  untouched.
- The operator's complete vulture file is not safe to paste verbatim because it
  contains autonomous write/purge/restore/subprocess/mutation organs.
- No current blocker for Phase 4 after this follow-up is reviewed/committed,
  provided security veto remains deterministic and council memory remains
  advisory evidence.

## Active Files
- `aios/maintenance/vulture_sanitation.py`
- `tests/test_vulture_sanitation.py`
- `.aios/state/RESUME.md`
- Phase 4 should begin with a fresh task/lease and targeted tests.

## Notes Not Yet Promoted
- Vulture output is proposal/evidence only. It cannot activate trusted memory,
  authorize action, mutate policy, write files, call cloud providers, run tests,
  purge, restore, or invert pheromones.
- Phase 4 should add signal ganglia and council memory as typed
  adapters/evidence around the existing council call chain, with deterministic
  security veto strongest.
