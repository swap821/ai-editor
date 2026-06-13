# FIDELITY baseline — superbrain ⇄ classic integration

**Canon tag:** `pre-integration-canon-v1` (the rollback point; the pre-integration
state of both UIs). Created at the start of the integration work (design **A**:
superbrain-as-lead, a *home form* + a *manufacturing form*).

## The two surfaces to compare (parity is proven in the operator's browser — FIDELITY law)
- **superbrain home** — default mount: `http://localhost:5173/`
- **classic IDE** — `http://localhost:5173/?ui=classic`

## Capturing a baseline / before-after (operator's browser is authoritative)
1. `cd frontend && npm run dev`
2. (optional) backend for live data: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
3. Screenshot each URL above at 1920×1080 after it settles (~12s for the superbrain boot).
   A documentary headless shot is also available via the lab harness
   (`GAG demo/gag-orchestrator/tools/capture-product.mjs`, puppeteer → `goldens/`).

## What each phase touches (so a reviewer knows when goldens matter)
- **Phase 0** — this baseline + canon tag. No pixels move.
- **Phase 1** — backend boundary only (base URL, auth, session, SSE, approval; +`earned_autonomy`
  in the classic). **No visual change** — goldens unchanged.
- **Phase 2+** — the composition shell + the manufacturing dock + the glamorize work **move pixels**.
  Capture before/after in the operator's browser, canon-tag + goldens before each visual change.

> Rule (FIDELITY IS SACRED): no auto-degrade, the operator's assets/scene untouched,
> the superbrain is polished by micro-detailing — never redesigned — and every visual
> change carries before/after screenshots proven in his browser.
