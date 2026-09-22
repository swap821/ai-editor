# V1 Honest Picture and Newcomer-Ready GAGOS

## Global constraints

- Preserve the 3D living being as the canonical front door.
- Beginner mode is the default; Expert/Mirror mode is explicit.
- Support plain language, guided tasks, and voice entry; typed/UI approval remains authoritative.
- Use the existing mirror read model and event registry as the only operational truth boundary.
- Never touch `aios/security/*` or weaken the gateway, scope, secret, audit, or injection controls.
- Never hand-edit generated `frontend/src/superbrain/` files; product-authored seams and the lab-to-product port remain the only valid paths.
- Treat the existing dirty worktree as user/peer-owned unless a changed path is created by this plan.

## Tasks

### Task 1 — Truth dossier and current architecture currency

Create the current V1 truth dossier and beginner/expert experience specification. Update only current-facing architecture/readme references that still describe deleted UI routes. Record current test evidence and explicitly preserve historical documents.

Expected: docs identify the single root UI, canonical mirror endpoints, current backend authorities, known unavailable/unproven surfaces, and release gates without claiming runtime proof from source presence.

Verification: `git diff --check`; targeted `rg` contradiction scan.

### Task 2 — Experience mode contract

Add a product-authored, local-persisted Beginner/Expert mode contract with deterministic default `beginner`, accessible mode switch, and tests for default, persistence, invalid values, and storage failure.

Expected: mode is a small pure contract with no backend authority or mutation side effects.

Verification: focused Vitest plus full frontend test suite.

### Task 3 — Beginner front door and Expert/Mirror reveal

Wire the mode into `SuperbrainApp`, `GagosChrome`, and `LivingWorkspaceShell`. Beginner mode keeps the living being, conversation, voice, three starter paths, approvals, and active work surfaces; it hides dense operator navigation and implementation controls. Expert mode exposes the existing mirror/workbench surfaces and truth status. Add accessible tests for switching and truthful mode-specific visibility.

Expected: no duplicate conversation owner, no loss of approval/action surfaces, and no fabricated state.

Verification: focused component tests, typecheck, full frontend suite, build.

### Task 4 — Voice-inclusive newcomer contract

Make the beginner copy and controls explicitly explain that voice is conversational assistance and cannot authorize risky actions. Cover unavailable browser speech, backend voice failure, interruption, language toggle, and approval separation with tests. Do not change the security authority or spoken-action boundary.

Expected: a spoken approval phrase never changes pending approval state; explicit approval remains available.

Verification: focused voice/approval suites plus full frontend suite.

### Task 5 — Local installer/pilot truth surface

Add a small product-authored first-run readiness surface backed by the existing bootstrap/readiness endpoints. Distinguish ready, unavailable, and blocked states; link to recovery guidance; never imply that source presence equals runtime proof. Keep the existing launcher/Compose security model unchanged.

Expected: a clean local install can understand what is missing before attempting a task.

Verification: frontend contract/component tests and existing backend bootstrap/readiness tests.

### Task 6 — Final evidence and handoff

Run backend and frontend verification, canon guards, and docs scans. Update `.aios/state/RESUME.md` and append an Experience Object. Do not commit, merge, push, or alter unrelated dirty paths.

Expected: evidence is fresh, failures are reported honestly, and the next action is singular and actionable.

Verification: live command outputs recorded in the ledger and final self-review.

