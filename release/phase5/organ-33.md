# Phase 5 proof — Organ 33: Model Registry and Capability Passport

**Status under re-read:** `green`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `9408fd03e2697d5142c05d9ef993aa92337343ff`
**Generated:** 2026-10-29T05:20:53+00:00

## Mechanical failures (enforceable subset)

- **C10**: cited test tests/test_local_clerk_integration.py::test_the_local_runtime_is_actually_reachable did not run and pass
- **C10**: cited test tests/test_local_clerk_integration.py::test_a_real_local_model_answers_a_real_prompt did not run and pass
- **C10**: cited test tests/test_local_clerk_integration.py::test_the_qualification_suite_runs_against_a_live_model did not run and pass
- **C10**: cited test tests/test_local_clerk_integration.py::test_the_dispatcher_honours_the_live_verdict did not run and pass
- **C10**: cited test tests/test_local_clerk_integration.py::test_deterministic_code_still_wins_over_a_live_model did not run and pass
- **C10**: cited test tests/test_local_clerk_integration.py::test_the_live_verdict_is_recorded_as_evidence did not run and pass
- **C10**: cited test tests/test_model_passport_live_integration.py::test_reconcile_discovers_the_live_model_rather_than_a_seeded_row did not run and pass
- **C10**: cited test tests/test_model_passport_live_integration.py::test_the_passport_faithfully_projects_a_real_qualification_run did not run and pass
- **C10**: cited test tests/test_model_passport_live_integration.py::test_a_role_the_live_evidence_does_not_back_is_refused did not run and pass
- **C10**: cited test tests/test_model_passport_live_integration.py::test_an_unregistered_model_has_no_passport did not run and pass

## Written verdict keys that are not PASS/N/A

(none — written verdicts PASS/N/A)

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
