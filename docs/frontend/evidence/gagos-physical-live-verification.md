# GAGOS Physical Embodiment — Live Verification Evidence

Captured 2026-09-24 after the authenticated approval-hold and approved-write
runs. The test artifact was disposable and was removed after each run.

## Supported container path

With the normal `AIOS_APPROVED_EXECUTION_BACKEND=container` configuration, the
same authenticated ceremony and exact create-file capability replay reached a
real `verify_result` with `verdict=fail`. The durable disposable cortex bus
also recorded:

```text
verification.completed  status=failed  trust=verified  passed=false
```

The verifier reported that the Docker API was unavailable. This is a truthful
fail-closed production-mode result: the write was not treated as verified.

## Explicit development path

To prove the verifier path itself without changing repository source, a second
fresh disposable service used the documented development-only host backend with
`AIOS_VERIFY_RUNNER=pytest` and the project venv first on `PATH`. The command
remained scope-compatible; no absolute interpreter path was passed to the
approved action.

The authenticated replay then streamed `verify_result` with:

```text
verdict=pass
target=training_ground/test_physical_approval.py
[VERIFY PASS] 1 passed, 0 failed (exit 0) (strength=STRONG)
```

The stream ended with `done`, and the disposable cortex bus recorded:

```text
verification.completed  status=success  trust=verified  passed=true
turn.completed           status=completed
```

The generated test file was removed after inspection. This proves the complete
approval → audited write → forced verification → durable verified outcome path
under the explicit development runner. It is not a claim that the default
container backend is available on this machine.

These runs do not prove live worker swarm lifecycle, product-hardware
performance, screen-reader behavior, operator visual acceptance, or three-person
human validation.
