# Phase 5 proof — Organ 23: Release Conformance Organ

**Status under re-read:** `green`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `aea675025b2e8ade58db001d1960157865ff9e95`
**Generated:** 2026-09-20T19:40:51+00:00

## Mechanical failures (enforceable subset)

- **C6**: focused_tests FAILED: tests/test_organ_release_conformance.py (4: test_organ_proof_manifest_hash_pins_the_ledger, test_shipped_manifest_is_a_fully_honest_pin, test_build_release_manifest_check_passes_against_the_shipped_manifest, test_verify_organ_contracts_passes_on_the_shipped_ledger_and_manifest)
- **C7**: integration_tests FAILED: tests/test_organ_release_conformance.py (4: test_organ_proof_manifest_hash_pins_the_ledger, test_shipped_manifest_is_a_fully_honest_pin, test_build_release_manifest_check_passes_against_the_shipped_manifest, test_verify_organ_contracts_passes_on_the_shipped_ledger_and_manifest)
- **C10**: cited test tests/test_organ_release_conformance.py::test_verify_organ_contracts_passes_on_the_shipped_ledger_and_manifest did not run and pass
- **C10**: cited test tests/test_organ_release_conformance.py::test_build_release_manifest_check_passes_against_the_shipped_manifest did not run and pass

## Written verdict keys that are not PASS/N/A

(none — written verdicts PASS/N/A)

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
