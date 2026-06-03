# PLAN.md — Path to a 90%+ P0–P1 MVP (evidence-based)

> Phase 2 plan. Authored by Claude Code on **2026-06-03**, grounded in
> `.aios/state/AUDIT.md` (verified ground truth: **111 passed, 1 skipped, 83%
> coverage**; backend core ≈80%, whole demoable MVP ≈62%).

## Context
The audit showed the backend backbone (security, memory, audit, reflection,
rollback, planner, executor, agentic loop) is BUILT and test-backed. What gates a
**demoable** MVP is a short, specific set of P0–P1 gaps — chiefly the user-facing
edit/diff path, the absence of any frontend tests, an unasserted slice of the API
contract, and the missing Verifier stage. This plan closes those, one component
per slice, **tests before code**, to reach a 90%+ P0–P1 MVP in ~8 solo-dev weeks.

**Operating rules for execution (Phase 3):** one slice at a time; I restate the
slice and **wait for your explicit OK before writing any code**; verify (tests
green) → checkpoint `RESUME.md` → next. Approvals stay ON; never
`--dangerously-skip-permissions`. **Frozen core (security/audit):** Slice 6 touches
`gateway.py` and needs your explicit go before I touch it. Target is 90%+, **not**
"100%/fully built".

## Slices (each: tests-first; "Done when" = a concrete passing check)

| # | Slice (one component) | Closes (AUDIT) | Done when |
|---|---|---|---|
| **1** | **Lock the security + API contract.** **(1a — FROZEN CORE, needs explicit go)** fix the `scope_lock.command_stays_in_scope` bypasses found in the xhigh review: `~/…` home paths, absolute paths glued to a word by a shell metachar (`>` `;` `\|` `&`), and bare `..` currently classify **in-scope/GREEN** (verified live). **(1b)** direct HTTP tests for `/api/v1/{plan,execute,approval/req,rollback}` (fakes via `Depends`). | review **F1–F4**, P0-3 | regression tests prove `cat ~/.ssh/id_rsa`, `echo x>/home/u/.bashrc`, `cat foo;/etc/passwd`, and `cat ..` all classify **RED**; the Windows-only backslash test gets a `skipif` + a cross-platform forward-slash twin; existing scope tests stay green; 4 new `test_api.py` route cases pass; **full suite green**. |
| **2** | **File-edit tool + unified diff (backend)** — agent tool that scope-resolves the path, builds a `difflib` unified diff, classifies YELLOW, snapshots via the rollback engine *before* writing, applies only on approval, audits + secret-scrubs. | P0-1a | New `tests/test_file_edit.py`: (i) edit yields a diff preview + pauses YELLOW (`human_required`); (ii) on approval the file content matches; (iii) out-of-scope path refused; (iv) a pre-write rollback snapshot exists (revertible). |
| **3** | **Frontend test harness** — add Vitest + React Testing Library; wire `npm test`. First tests: `MessageBubble` renders `{msg}`; SSE reader parses `step/text_chunk/code/human_required/done`; approval bar renders for a pending action. | P0-2a | `npm test` exits 0 with ≥3 passing tests; `npm run build` clean. |
| **4** | **Diff preview in approval UI + e2e happy-path** — approval bar renders the slice-2 unified diff (not just the command); record the full live walk. | P0-1b, P0-2b | Frontend test asserts the approval bar shows a diff block for an edit action; the manual e2e (chat → file-edit YELLOW → diff → approve → write → reflect) is recorded passing in `RESUME.md` (RAM-gated, operator-run). |
| **5** | **Verifier stage** — `aios/core/verifier.py`: runs a verification command (pytest/jest) on an execution, parses pass/fail + counts, computes a delta, returns a structured result; a failed verify feeds the existing reflection hook. | P1-4 | `tests/test_verifier.py`: passing→`OK` + delta≥0; failing→`FAIL` + fires `on_failure` reflection + negative delta; parse/exit error fails-closed to `FAIL`. |
| **6** | **Prompt-injection vector blocklist** *(FROZEN CORE — needs your OK)* — add an embedding-similarity layer to `gateway.py`'s injection shield (curated dataset embedded once; cosine ≥ threshold → RED), dual-layer with regex, deterministic, fail-closed preserved. | P1-5 | `tests/test_security.py`: a semantically-novel injection that matches **no** regex is classified RED by the vector layer; all existing regex + fail-closed + scope + rate-limit tests still pass. |
| **7** | **L3 entity facts + contradiction detection** — store optional `(subject,predicate,object)` facts; on write, query same subject+predicate; on conflict route to reflection/human instead of silent commit (blueprint §5.3). | P1-6, P1-7 | `tests/test_memory.py`: a conflicting fact (same subj+pred, new obj) is detected and **not** silently committed; a non-conflicting fact commits + syncs FAISS. |
| **D1** | **RED-policy — DECIDED 2026-06-03: keep hard-block.** RED is *always* refused, even after human approval (`execute_approved` refuses RED) — deliberately stricter than the blueprint §6.1 typed-token spec (fail-closed by choice). | P1-8 | ✅ **Done** — invariant already pinned by `tests/test_executor.py::test_execute_approved_still_refuses_red`; recorded in memory `red-zone-hard-block-policy`. Slice 1b's `/approval/req` test asserts it at the HTTP layer. |

## Week-by-week (8 weeks, solo, 1 slice/week; week 8 = freeze)
- **W1:** Slice 1 — **security-scope hardening first** (1a, frozen core, needs go) then API contract tests (1b) + Decision D1 (settle RED policy). The scope bypasses are live security holes, so they lead.
- **W2:** Slice 2 (file-edit + diff backend — the highest-value missing capability).
- **W3:** Slice 3 (frontend test harness — prerequisite for slice 4).
- **W4:** Slice 4 (diff-preview UI + e2e happy-path — the signature demo moment).
- **W5:** Slice 5 (Verifier stage).
- **W6:** Slice 6 (injection vector blocklist — *gated on your OK to touch the core*).
- **W7:** Slice 7 (L3 entity facts + contradiction detection).
- **W8:** Polish only — fix known bugs, full suite green, rehearse the 2-min demo, update README/RESUME. **No new features** (blueprint §11/R2 feature-freeze discipline).

After W4 the *demoable* MVP should already clear ~90% of the recruiter-demo path
(architecture → YELLOW diff gate → error intercept → reflection → audit-chain
break). W5–W7 raise core fidelity; W8 is reliability.

## Later phases (toward 100%, sequenced AFTER the core is green — not dropped)
Voice (Whisper/Piper) · Project Knowledge Graph (Neo4j) · Docker Compose +
Prometheus/Grafana/OpenTelemetry · chaos/perf/automated-adversarial test tiers.
(AWS Bedrock cloud routing is already BUILT and stays opt-in.)

**Frontend-polish worker (operator idea, 2026-06-03):** a task-scoped sub-agent that
proposes UI improvements (iterating in the CodeCanvas / live-preview loop) so the backend
brain stays the human's focus. Safe-by-construction on the pipeline we're already building:
its edits ride the **same `edit_file` → unified diff → human approval → pre-write snapshot →
audit** path (Slice 2/4); it must keep `npm test` + `npm run build` green (Slice 3) or the
diff is rejected. It is **propose-only, approval-gated, and externally scheduled** — never an
autonomous daily self-driver (a prompt can't self-trigger — blueprint A1; unattended = plan-only,
A4). Scope it only once the core MVP is green.

## Definition of done for the whole plan
Full suite green on every checkpoint; new slices each ship their own passing tests;
frontend `npm test` + `npm run build` green; the live e2e happy-path recorded
passing; AUDIT.md re-run shows the P0 + most P1 rows moved to BUILT. Honest target:
**≈90% of the P0–P1 MVP** — reported as such, never "100%".

---
_Phase 2 complete. STOPPING for your approval. On "go", Phase 3 starts at **Slice 1**
(I'll restate it and wait again before writing code)._
