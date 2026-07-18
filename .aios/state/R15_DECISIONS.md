## Decision 2026-07-19 — Maintenance resolution requires structured governed evidence

- `MaintenanceLifecycleEngine.resolve_after_rescan()` is the only resolution transition. It requires the authoritative completed mission, exact contract/action/workspace/diff bindings, a promoted `PromotionResult`, current `VerificationAuthority` results, and the exact completed scanner rescan proving fingerprint absence.
- The former free-form `attempt_resolution()` path is retained only as a fail-closed compatibility surface; every caller is refused.
- This adds no maintenance authority. MissionService, VerificationAuthority, PromotionAuthority, the existing durable repositories, and the lifecycle engine retain their constitutional ownership.

## Decision 2026-07-19 — Deterministic maintenance verification is a fixed registry

- `maintenance.rescan` is represented by a typed `VerifierSpec` and dispatched by `VerifierRegistry` over an injected, identity-bound scanner adapter.
- The registry is an application dispatcher and evidence producer, never a permission or promotion authority. It emits structured argv for provenance only; it does not parse or execute shell text, accept learned commands/images, or permit network/git-history access.
- A registry fixture/integration pass is not live private-Executor proof. That distinction remains explicit in the runtime proof and acceptance matrix.

## Decision 2026-07-19 — Skill verification is typed and fail-closed

- `skill.reuse` is represented by a frozen, versioned `SkillVerifierSpec` and is carried into governed local-reuse mission contracts as a typed verifier, never as a command string.
- Legacy persisted free-text verification plans are quarantined at load and cannot satisfy applicability. They require structured re-qualification before activation; no silent migration grants authority.
- Skill applicability remains a domain gate and does not execute, authorize, or promote work. MissionService, WorkerFoundry, VerificationAuthority, PromotionAuthority, and MemoryAuthority retain their constitutional ownership.

## Decision 2026-07-19 — Gemini zero thinking budget is provider-default

- A live Vertex call showed that the discovered `gemini-2.5-pro` route rejects an explicit `thinking_budget=0`.
- `GeminiClient` now sends `thinking_config` only for a positive budget; zero and negative values omit the override so model-specific provider validation remains authoritative.
- The repair is limited to the existing adapter and is covered by non-streaming and streaming tests. It does not weaken privacy, routing, capability, verification, or execution authority.
