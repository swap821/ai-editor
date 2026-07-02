# FRONTEND BEAUTIFICATION BLUEPRINT — chrome polish to the being's level

**Date:** 2026-07-03 · **Author:** Claude (Fable, supervising) · **Builder:** Codex (waves, one hash-pinned handoff each) · **Reviewer:** Claude · **Final eye:** the operator at :5173 — always.

**Mandate (operator, 2026-07-03):** "there is still some visual flaws u can sense it and make it beautiful i want beautification polish." Process he chose: Claude writes the blueprint, Codex codes, Claude reviews.

**The honest read:** the BEING is premium; the DOM chrome around it lags. The loudest tell is the council panel (flat admin card = One-Law violation); then trail/status/dock micro-states; then unauthored motion. Grounded in a five-lens audit (39 raw → 27 synthesized findings, wf_85123c7e) + live screenshots from the witnessed-demo session.

---

## 0. LAWS (violating any = the handoff is rejected in review)

1. **The poster tetrad is the only palette:** cyan `#7bf5fb` / purple `#b06eff` / green `#54f0a0` / orange `#ff7e40` on true black. No new hues. No blues. `tools/check_css_canon.py` + `tests/test_canon_guard.py` must stay green.
2. **`frontend/src/superbrain/superbrain.css` is FROZEN** — never edit it (guard-enforced).
3. **The 3D being is untouched**: no geometry/shader/palette/posture changes. This blueprint is DOM chrome only.
4. **Materialization law:** chrome reads as grown from the being's anatomy — dark slabs, luminous etched text, no default-browser controls. No Monaco, no IDE chrome.
5. **Motion:** luminance-first, calm, authored; every animation has a `prefers-reduced-motion` path. Reuse existing keyframes (`hud-enter`, easings in tokens) before inventing new ones.
6. **Tests:** the full frontend suite + coverage (`npm run test:coverage`) must exit 0 on every handoff; new behavior gets a test. Never run `npm run port` (standing landmine).
7. **One writer:** Codex holds the builder lease per wave; Claude reviews on the hash-pinned tree; disagreements stop the wave, never fork it.

## 1. GROUND-TRUTH CORRECTIONS (read before building — two audit "P0s" are phantoms)

- **SYN-02 (duplicate "Holding for your approval" + trySubmit guard): STRUCK. Do not build.** Live DOM inspection proved the log renders each message exactly once (8 children, no duplicates — the "duplicate" was an a11y-extraction artifact: parent `StaticText` + child `InlineTextBox` share a name). The proposed mechanism is also wrong JS: an async function body runs synchronously to its first `await`; `busyRef.current = true` (GagosChrome.jsx:453) executes before any same-tick second caller reaches the line-448 check. Three lenses repeated this because the audit brief itself seeded the phantom — lesson recorded.
- **SYN-01/SYN-04 (cross-session bleed in the trail): REFRAMED — out of this blueprint.** The witnessed "foreign activity" was the operator's OWN turn: dev-events 341–351 all carry his directive signature; the cloud model renamed its artifacts across approval-resumes (reverse_string.py → string_reverser.py). No session filter goes into the chrome. The REAL underlying find — literal default session-id fallbacks (`'ui-session'` etc., aios/api/main.py:541-552,936,975,1058) collapsing distinct callers into shared memory buckets — is a backend trust-boundary item, filed in §5, not a polish task.
- **SYN-03 ([SENSITIVE] tokens): partially DONE** (commit `9ba2e55`: DOM-trail redaction chips + tests). Remaining half for Codex → W3.4 below (adapter-side `humanizeRedactionMarkers` so 3D/body-speech consumers of `publishStep` detail never carry raw tokens).

## 2. WAVE 0 — foundations & real defects (do first, smallest)

- **W0.1 = SYN-05 (P0):** define the four missing tokens in `frontend/src/styles/tokens.css`: `--neon-cyan:#7bf5fb; --neon-purple:#b06eff; --neon-green:#54f0a0; --neon-orange:#ff7e40;` (they're referenced 11× in GagosChrome.css but defined nowhere). Prerequisite for every wave below.
- **W0.2 = SYN-17 (P1, a11y defect):** mic listening-pulse ignores reduced-motion — fix selector to `.gagos-mic.is-listening, .gagos-mic.is-listening::after { animation: none; }` (GagosChrome.css:639).
- **W0.3 = SYN-27 (P3):** remove the dead reduced-motion rule at GagosChrome.css:640 (targets a non-existent animation).
- **Acceptance:** canon guard green; reduced-motion emulation shows a still mic while listening; suite green.

## 3. WAVE 1 — canon hygiene (kill every off-tetrad stray)

- **W1.1 = SYN-06 (P1):** dead blue `rgba(96,165,250,…)` → cyan tokens (CouncilDashboard.css:422-423; GagosChrome.css:678 intent-browse tint — pick cyan or green, must stay distinct from intent-code; flag the choice in the handoff for operator eyes).
- **W1.2 = SYN-07 (P1):** divergent cyans in `CyberCursor.module.css` (#5ce1e6 → `var(--accent)`) and `BootSequence.module.css` (→ tetrad cyan). superbrain.css itself stays frozen.
- **W1.3 = SYN-08 (P2):** `.gagos-bar.intent-command` yellow → `--neon-orange` (intents become code=cyan / browse=per-W1.1 / swarm=purple / command=orange). Verify legibility beside the send button's orange busy state.
- **W1.4 = SYN-10 (P1, LAST in wave):** widen `check_css_canon.py` RENOVATABLE_GLOBS with `frontend/src/superbrain/components/**/*.css` so CI sees these files forever. MUST land after W1.1–W1.3 or CI immediately reds.
- **Acceptance:** repo-wide grep shows zero off-tetrad accent literals in editable chrome CSS; widened canon guard green.

## 4. WAVE 2 — the council panel becomes anatomy (the loudest fix)

- **W2.1 = SYN-12:** panel shell → materialized slab: radius 14px (or `--radius-lg` per SYN-20 if operator approves), cyan edge glow + inset top light, `hud-enter` entrance (reuse keyframe superbrain.css:1470 — do not redefine).
- **W2.2 = SYN-11:** form fields + Send to Council → etched-recessed treatment (inset shadows, cyan focus halo, styled placeholder) per the synthesis recipe; no default-browser controls left.
- **W2.3 = SYN-13 (P0-motion):** authored entrance for `.council-dashboard` (450ms, 80ms stagger) and `.swarm-hud` (400ms) via `hud-enter`; reduced-motion path required.
- **W2.4 = SYN-19:** bespoke `:focus-visible` cyan halo for Approve/Reject/Rollback/Send buttons (recipe in synthesis).
- **W2.5 = SYN-22:** mission cards get the inset etch; `.is-selected` gets the cyan ring+glow; empty-state gets a dashed etched frame.
- **W2.6 = SYN-23 (P3):** danger-only badge glow (`.is-danger`), OK/WARN stay flat.
- **Acceptance:** side-by-side screenshot vs tonight's baseline (screenshot_20260703_000035.852.jpg); the panel must read as the being's tissue, not an admin card. Operator's eye on :5173 gates the wave.

## 5. WAVE 3 — status chrome + chat dock

- **W3.1 = SYN-14:** `.gagos-pill` status cluster → verify-toast chip language (pill, tinted bg/border/glow per state; model chip purple, supervised green).
- **W3.2 = SYN-15:** model/provider hierarchy in the chip (name full-opacity, provider ~0.6) + ellipsis guard (max-width 220px).
- **W3.3 = SYN-16 (after W3.1):** drop the stray mobile padding re-add; fold into chip responsive sizing.
- **W3.4 = SYN-03-remainder:** `humanizeRedactionMarkers()` in aiosAdapter.ts `publishStep` (~line 95-151) so `detail` fields feeding 3D/body labels replace scanner tokens with "(a sensitive value was withheld)". Keep the marker regex as ONE named constant; do not weaken redaction. Extend aiosAdapter.dispatch/sse tests.
- **W3.5 = SYN-26:** visible calm "thinking…" echo above the dock during thinking/streaming (reuse `.gagos-typing` dots; sr-only status stays).
- **Acceptance:** chip states demoed in all four (local/cloud/supervised/offline) postures; suite green.

## 6. WAVE 4 — motion niceties (small, each with reduced-motion path)

- **W4.1 = SYN-18:** verify-toast authored exit (mirrored keyframe, ~250ms leaving state).
- **W4.2 = SYN-21:** refresh icon spin on MANUAL refresh only (separate `manualRefreshing` state; background poll never spins it).
- **W4.3 = SYN-24:** 220ms luminance settle on council risk/verdict tone changes (never soften a RED escalation into missability).
- **W4.4 = SYN-25:** mission-detail cross-fade via React `key` remount (220ms).

## 7. OPERATOR-DECISION ITEMS (present, don't auto-build)

- **SYN-09:** offline/fail dot is non-tetrad red `#f87171` — keep red as a deliberate out-of-palette hard-failure signal, or move to poster orange? (I lean: keep red — failure SHOULD break the palette.)
- **SYN-20:** unify the two radius scales via tokens (`--radius-lg`/`--radius-md`/`--radius-sm`) — needs his live look, lands with W2 if approved.
- **W1.1 browse-tint hue** (cyan vs green).

## 8. OUT OF SCOPE — filed as backend workstream (not Codex, not this blueprint)

1. **Approval-resume re-planning seam (top priority):** each resume re-invokes the model after grants pre-apply → filename drift, duplicate artifacts, 9 pauses/turn, final `unverified` despite green pytest. Resume should replay the approved plan, not re-ask. (Witnessed 2026-07-03; dev-events 341–351.)
2. **Literal default session-id fallbacks** (main.py:541-552 + Field defaults) — distinct callers share memory buckets; needs its own adversarially-reviewed PR.
3. **Secret-scanner filename false-positive** (`test_…py` → `test_[SENSITIVE: …].py` in audit lines + approval payloads).

## 9. PROTOCOL

One wave = one Codex handoff: builder lease via `agent_coord.py`, tests+canon+coverage green locally, hash-pinned tree, review request. Claude reviews within the session it lands: code diff + live :5173 screenshots (WebBridge) + guard runs. Waves 2/3 additionally gate on the operator's eye. Anything Codex finds beyond scope: report in the handoff, never freelance. If Codex is unavailable, the same waves run through Claude's Sonnet workflow fleet under identical review — the blueprint doesn't change.
