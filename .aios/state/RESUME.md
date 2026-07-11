# CI Green Checkpoint

**Current Goal:** Make GitHub `CI` green on `master` after failing run `29101145237` for commit `a98e241`.
**Last Completed + Verified Step:** Pushed `aa333a2 fix(ci): restore master checks` to `origin/master`. GitHub `CI` run `29119612045` passed (backend + frontend), and `CodeQL Advanced` run `29119612047` passed. Local pre-push gates also passed: backend coverage 91.78%, frontend lint 120/124 warnings, typecheck, Vitest coverage, and production build.
**Single Next Action:** No CI action remains; optional reviewer can inspect `aa333a2` and the GitHub runs above.
**Open Approvals / Blockers:** No CI blocker. Local-only dirty files remain: `.aios/memory/experiences.jsonl` has uncommitted journal entries, and `audit_report.md` is untracked from before this CI fix.
**Active Files For This Slice:** `aios/api/main.py`, `frontend/src/superbrain/SuperbrainApp.jsx`, `frontend/src/superbrain/components/canvas/{NervousSystem.tsx,NodeLattice.test.ts,SubsystemErrorBoundary.tsx,SuperbrainScene.LEGACY.tsx}`, `frontend/src/superbrain/core/CortexEngine.tsx`, `.aios/state/RESUME.md`.
**Notes Not Yet Promoted:** The backend fix avoids Starlette route-resolution timing by compiling rate-limited FastAPI templates to deterministic regexes. The legacy scene lint exemption is scoped to the rollback snapshot; active modules still lint normally.
