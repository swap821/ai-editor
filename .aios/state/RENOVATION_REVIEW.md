# RENOVATION REVIEW — operator eyeball harness (Waves 0–9)

> Branch `feat/frontend-renovation`. The agent cannot prove visual parity — this is the
> fast checklist to verify the whole renovation in YOUR browser. The renovation is
> **additive only**: the canon brain / voyage / scene / sovereignty row must read
> **UNCHANGED**; everything new lives behind a small top-right **▣ ORGANS** tab and a
> deferred approval safety-net. Soul anchor: *an autonomous agentic AI-OS superbrain
> constantly working with its tools, moving forward in deep-vast infinite space.*

---

## 1. How to run

```
cd frontend && npm run dev
```

| URL | Face | What it is |
|---|---|---|
| `http://localhost:5173/` | **default home** | canon `SuperbrainApp` + ▣ ORGANS dock + approval safety-net (additive) |
| `http://localhost:5173/?ui=shell` | **embedded forge** | `SuperbrainShell` (home/manufacture) + same dock + safety-net |
| `http://localhost:5173/?ui=classic` | **classic IDE** | legacy fallback, untouched by this renovation |

**Backend must be on `:8000`** for live organ data: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000` (from repo root). With no backend, every organ must show an explicit OFFLINE state — never fabricated rows (that is itself a check, see §3 offline drill).

---

## 2. Per-wave WHAT-CHANGED (Waves 0–9)

| Wave | One-line change | Files |
|---|---|---|
| **0a** | Canon-freeze guard derived from the real port manifest (whitelists the legal seam) | `tools/check_canon_frozen.py`; blueprint `.aios/state/FRONTEND_RENOVATION_BLUEPRINT.md` |
| **0b** | CSS-canon lint + `forge.css` brought to canon tokens / paint-trap-safe | `tools/check_css_canon.py`, `frontend/src/workbench/forge.css` |
| **1** | Organs dock shell + first two organs (Autonomy Ledger, Curriculum); mounted on `?ui=shell` | `workbench/organs/{OrgansDock,AutonomyLedgerPort,CurriculumPort}.jsx`, `organs.css`, `SuperbrainShell.jsx` |
| **2** | +3 organs (Skills, Proposals, Memory Search) | `workbench/organs/{SkillsPort,ProposalsPort,MemorySearchPort}.jsx`, `_fmt.js`, `organs.css` |
| **3** | +3 organs (Zone Probe, Plan, Models) + grouped section nav (replaces the flat row that broke past 8 organs) | `workbench/organs/{ZoneProbePort,PlanPort,ModelsPort}.jsx`, `OrgansDock.jsx`, `organs.css` |
| **4** | Mount the organs dock on the **default home** (`/`) — same dock, now on the bare canon face | `superbrain/SuperbrainApp.jsx` (mount line only) |
| **5** | Conversation/Answer organ — the verbatim last reply from L2 episodic memory; unread-answer dot; default tab = `converse` (P0 perception gap) | `workbench/organs/ConversationPort.jsx`, `OrgansDock.jsx`, `organs.css` |
| **6** | Approval safety-net — deferred fallback resolver for a missed `approval-required` event; mounted on **both** faces | `workbench/approval/{ApprovalSafetyNet.jsx,approval-safety-net.css}`, `SuperbrainApp.jsx`, `SuperbrainShell.jsx` |
| **7** | CSS-debt cleanup — `shell.css` to canon (glass recipe + indigo→cyan accent); lint scoped to live superbrain files | `frontend/src/workbench/shell.css`, `tools/check_css_canon.py` |
| **8** | (flagged in Wave 7) removal of 4 dead style files: `styles/{App,design-system,nexgen-3d,nexgen-layout}.css` — confirm nothing imports them | `frontend/src/styles/*` |
| **9** | INTENT/ALIGNMENT organ — read-only window into the latest per-turn `UnderstandingFrame` (`/conversation/session`, `limit:1`); intent + gloss, confidence meter, goal, ASSUMPTIONS/UNKNOWNS/CONSTRAINTS/DECISIONS, next_action, `CORRECTED` badge; loud clarifying-question banner when `ambiguity_action==='ask'`. 10th organ. | `workbench/organs/{IntentPort,OrgansDock}.jsx`, `organs.css`, `OrgansDock.test.jsx` (29 tests green) |

> Note: the live commit log is labeled through Wave 8 (`Renovation Wave 8: convergence …`). Wave 9 (the INTENT organ) is the latest build; confirm its commit landed alongside this doc. Verify the full range with `git log --oneline pre-renovation-baseline-2026-06-14..HEAD`.

---

## 3. BROWSER CHECKLIST (grouped by face)

### A. Default home — `http://localhost:5173/` (with backend on :8000)
- [ ] Page loads to the **canon voyage** — brain moving forward, scene/sovereignty row look exactly as before (only addition: a small **▣ ORGANS** tab, top-right under the topbar).
- [ ] If the brain has earned autonomy, the tab shows a live **⚡N** chip; on a real CAPABILITY EARNED / AUTONOMOUS ACTION / SKILL MASTERED event the pip **flares**.
- [ ] Click **▣ ORGANS** → glass panel opens; click the section header (SECTION + organ name + ▾) → the **grouped organ menu** slides down.
- [ ] Walk all **10 organs** — each shows **REAL data** or an **honest empty / offline** state (never fabricated rows):

  | Organ (menu group) | Source | Real-data check / honest empty |
  |---|---|---|
  | **Conversation** (CONVERSE) | `POST /api/v1/conversation/session` | the verbatim Q→A log (see B); empty: "No dialogue yet this session" |
  | **Autonomy** (GOVERNANCE) | `GET /api/v1/development/autonomy` | earned/probation/revoked rows + `min_successes` threshold + failure_count/timestamps; empty: honest "no earned classes" (feature ships OFF) |
  | **Proposals** (GOVERNANCE) | `GET /api/v1/self-analysis/proposals?status=proposed` | self-analysis fixes w/ diff; empty: "No open proposals…" |
  | **Growth** (LEARNING) | `GET /api/v1/development/curriculum` | skill→level→task ladder, held-out pills; empty: "No curriculum defined yet" |
  | **Skills** (LEARNING) | adapter `getKnownTrails()` poll | verified workflows + success rate; empty: brain has none |
  | **Memory** (MEMORY) | `POST /api/v1/memory/search {query,top_k:8}` | type a query → scored star-rows w/ provenance; empty: "No memories matched …" |
  | **Plan** (REASONING) | `POST /api/v1/plan {goal}` | confidence-gated step tree + AUTO/HUMAN verdict; idle until you submit a goal |
  | **Intent** (REASONING) | `POST /api/v1/conversation/session {limit:1}` → `alignment` | latest `UnderstandingFrame`: intent + gloss, confidence meter, goal, assumptions/unknowns/constraints/decisions, next_action, `CORRECTED` badge, loud clarifying-question banner when ambiguity=ask; empty: "No understanding frame yet this session"; offline: "INTENT OFFLINE" / quiet "· link offline" keeping the last frame |
  | **Zone Probe** (SECURITY) | `POST /api/v1/security/classify {command}` | type a command → GREEN/YELLOW/RED + reason; idle until you probe |
  | **Models** (SYSTEM) | `GET /api/v1/models/{local,bedrock,gemini,auto}` | per-provider readiness; empty: "No brains ready…" |

### B. Conversation organ — the verbatim reply
- [ ] Send a directive from the command bar (use `?ui=shell` → Enter workbench for the in-scene command line, or classic).
- [ ] Open ▣ ORGANS → **Conversation**: the **last assistant reply is shown verbatim** (full, not the 160-char terminal stub), oldest→newest, code fences rendered as code blocks. It pulls L2 episodic memory, so it captures turns it didn't originate.
- [ ] Turn finished while you were elsewhere → the tab shows a quiet **unread-answer dot**; opening Conversation clears it.

### C. Approval safety-net (the stuck-run fix)
- [ ] Trigger a **YELLOW write** (a directive that edits a file → backend pauses for approval).
- [ ] Confirm the **canon ApprovalPanel** surfaces with AUTHORIZE/REJECT + diff — the healthy path.
- [ ] If the canon panel does NOT appear within ~1.5s (missed bus event), the **safety-net surfaces a RESOLVE control** ("RESOLVE PENDING APPROVAL" card, eyebrow *recovered from a missed approval signal*) with AUTHORIZE/REJECT + the same diff. Exactly **one** resolver must be visible — never two panels in the healthy path.
- [ ] AUTHORIZE or REJECT clears it; the run proceeds / stands down (no hang).

---

## 4. EYEBALL-PENDING — scrutinize (FIDELITY)

- [ ] **▣ ORGANS tab placement on the bare home (`/`)** — it self-portals to `document.body` (not the canon `#hud-portal-root`), z-index 55, below the canon command/approval band (z 60). Confirm it sits cleanly top-right, does **not** overlap the sovereignty row or topbar, and never sits *above* a live approval control. This is the riskiest stacking-context check (Wave 4 put the dock on the canon face for the first time).
- [ ] **`?ui=shell` accent shift indigo→cyan + glass recipe** (Wave 7) — the shell command bar / Execute / voyage + mode-toggle dots / prompt caret moved from indigo `#6366f1` to canon `--accent` (cyan), and the glass moved to `blur(14px) saturate(140%) brightness(1.08)`. Confirm the shell reads as canon (one-accent cyan) and the glass doesn't milk out. Layout/geometry should be identical.
- [ ] **Answer prominence** — is the verbatim reply easy to find? It is behind ▣ ORGANS → Conversation (default tab), with an unread dot — confirm that reads as discoverable, not buried.
- [ ] **Canon UNCHANGED (the whole point)** — brain, voyage (`-Z` forward motion), scene, and the **sovereignty row FIDELITY·SKY·SURFACE·SOUND + the shield** must be **visually identical** to the baseline. Additive only — if anything canon moved or recolored, that's a regression. Compare `/` against the `pre-renovation-baseline-2026-06-14` tag.

**Offline drill (do once):** kill the backend, reload `/`, open each organ → every one must show its explicit `… OFFLINE — AI-OS unreachable` state, **never a fabricated row**.

---

## 5. ROLLBACK

| Lever | Value |
|---|---|
| Working branch | `feat/frontend-renovation` |
| Baseline tag (pre-renovation) | `pre-renovation-baseline-2026-06-14` |
| Canon-freeze guard | `python tools/check_canon_frozen.py` — exit 1 if any frozen canon path changed (whitelists `SuperbrainApp.jsx` / `SuperbrainShell.jsx`) |

- Inspect the renovation: `git log --oneline pre-renovation-baseline-2026-06-14..HEAD`.
- Full rollback: `git checkout master` (the renovation is isolated on its branch; nothing merged).
- Restore a single canon file from baseline: `git checkout pre-renovation-baseline-2026-06-14 -- <path>`.
- Before any commit on this branch, run `python tools/check_canon_frozen.py` and `python tools/check_css_canon.py` — both must pass. Backend baseline unchanged: `.venv\Scripts\python -m pytest -q`.
