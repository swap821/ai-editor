# ACTIVE-BRAIN BADGE — proposal (P3 UI; FIDELITY-gated)

**Authored 2026-06-14 — design-first, no code until you pick a path.**
The multi-LLM backend now emits, at the start of every `/api/generate` turn, an SSE frame:

```
event: route
data: {"provider":"gemini","model":"gemini-2.5-flash","privacy":"cloud","task":"reasoning","auto":true}
```

This is the **active-brain signal** — which brain served the turn, and whether it stayed local. The
badge renders it: *which provider/model is thinking right now, and is my code leaving the machine.*

---

## 1. The canon boundary (the thing that decides the plan)

The superbrain UI is **canon**: `frontend/src/superbrain/**` are byte-identical copies of the lab
(`GAG demo/gag-orchestrator`), **overwritten by `npm run port`**. They are NEVER edited in the product —
changes are authored in the lab and byte-synced. The classic IDE and `src/workbench/*` are product-safe.

| File | Role | Status |
|---|---|---|
| `src/App.jsx` (classic) `processEvent` + header | classic SSE handler + header badge | **PRODUCT-SAFE** ✅ |
| `src/workbench/*` (new files) | product overlays | **PRODUCT-SAFE** ✅ |
| `src/main.jsx`, `SuperbrainApp.jsx`, `SuperbrainShell.jsx`, `config.js` | mount/shell seam | **PRODUCT-SAFE** ✅ |
| `src/superbrain/lib/aiosAdapter.ts` | superbrain SSE consumer (`streamTurn` switch) | **CANON** (lab + port) ⛔ |
| `src/superbrain/lib/cognitionBus.ts` | event vocabulary (`CognitionEventType`) | **CANON** ⛔ |
| `src/superbrain/components/ui/SuperbrainHUD.tsx` | the topbar "sovereignty row" | **CANON** ⛔ |
| `src/superbrain/superbrain.css` | topbar styles | **CANON** ⛔ |

> The active brain *most wants* to live in the superbrain **sovereignty row** (the brain is the lead).
> But that row is canon — so it is a lab-authored + ported + FIDELITY-ritual change, not a product edit.

---

## 2. The two surfaces (mockups)

### Classic IDE header — `?ui=classic` (PRODUCT-SAFE)
```
 before:   [ Model ▾ ]   ● Auto · llama2          [ 🛡 Secure Gateway ]
 after:    [ Model ▾ ]   ◉ gemini-2.5-flash · CLOUD · auto   [ 🛡 Secure Gateway ]
                          └ dot: green = LOCAL, amber = CLOUD; "auto" tag only when auto-routed
```

### Superbrain sovereignty row — default mount (CANON)
```
 before:  ◍ CORE ONLINE  |  LATENCY 41ms  |  AUTONOMY ⚡1  |  FIDELITY SKY
 after:   ◍ CORE ONLINE  |  LATENCY 41ms  |  AUTONOMY ⚡1  |  BRAIN ◈ gemini-2.5-flash · CLOUD  |  FIDELITY SKY
                                                            └ BRAIN dot: cyan/green LOCAL, amber CLOUD
```
The `BRAIN ◈ <model> · <privacy>` segment matches the existing `.system-summary` idiom (status-dot +
`topbar-divider` + `<strong>` value), so it reads as a native part of the row, not a bolt-on.

---

## 3. Phase 1 — Classic badge (PRODUCT-SAFE, ship now, ~1–2h)

Zero canon risk; lands immediately behind `?ui=classic`.

- `App.jsx` `processEvent` (~line 793): add `else if (eventType === 'route') setActiveBrain(data)`.
- Add `const [activeBrain, setActiveBrain] = useState(null)`; reset on new turn.
- Header right cluster (~lines 1079–1118): drive the existing inference-status badge from `activeBrain`
  (live per-turn route), falling back to the selected-model display before the first turn.
- Reuse `PROVIDER_META` (ollama green, bedrock orange); add a `gemini` entry (Google blue/teal). Privacy
  dot = green(local)/amber(cloud).
- **Ritual (light):** before/after screenshot of the classic header in your browser. Not canon, no goldens.

## 4. Phase 2 — Superbrain sovereignty-row badge (CANON; the headline)

The faithful target — the brain announces itself in its own topbar. Authored in the **lab**, byte-synced
via `npm run port`. Two variants by how much canon they touch:

- **2A — integrated (recommended, more canon):** add the `BRAIN ◈ …` segment to `.system-summary` in
  `SuperbrainHUD.tsx`; the row subscribes to a new cognition `route` event; styles in `superbrain.css`.
  Native to the sovereignty row. Touches `aiosAdapter.ts` + `cognitionBus.ts` + `SuperbrainHUD.tsx` + `superbrain.css`.
- **2B — overlay (lighter canon):** only `aiosAdapter.ts` (publish) + `cognitionBus.ts` (type) change in
  canon; a NEW product component `src/workbench/ActiveBrainBadge.jsx` renders a fixed badge near the topbar
  and subscribes to the bus. Smaller canon footprint, but a floating element rather than a row segment.

Both need the canon adapter to publish the event (the superbrain SSE stream is consumed only by the canon
`aiosAdapter.streamTurn` switch — its `default` case currently drops unknown frames, so `route` needs a case):

```ts
// aiosAdapter.ts streamTurn() switch (CANON — lab edit + port)
case 'route':
  publishCognition({ type: 'route', label: 'ACTIVE BRAIN',
    detail: `${frame.data.provider}:${frame.data.model} (${frame.data.privacy})`,
    data: frame.data });
  break;
// cognitionBus.ts: add 'route' to CognitionEventType (CANON)
```

**FIDELITY ritual (mandatory for Phase 2):** re-confirm canon tag `pre-integration-canon-v1` → capture
goldens before (lab `tools/capture-product.mjs`) → author in lab → `npm run port` → before/after
screenshots at 1920×1080 in YOUR browser (superbrain home, settled) → verify the rest of the scene/nerves
are byte-unchanged → your assets untouched. Microdetailing, never redesign.

---

## 5. Recommendation + open decision

**Recommended:** Phase 1 now (product-safe, immediate value for the classic IDE), then Phase 2A as the
headline (the brain in its sovereignty row) through the full lab+port+screenshot ritual — since the
superbrain is the official, sovereign frontend.

**Open decision (operator):**
1. Path — **Phase 1 only** / **Phase 2A (integrated, recommended)** / **Phase 2B (overlay)** / **both 1 + 2A**.
2. For Phase 2, the final "parity proven in HIS browser" screenshot sign-off is yours; I can author the lab
   change + port + headless goldens, but you confirm the look.

_Grounded in: backend `event: route` (commit 43098f6); `App.jsx` processEvent (738–793) + header (1079–1118);
`SuperbrainHUD.tsx` `.system-summary` topbar; `cognitionBus.ts` (8-type union); `FIDELITY_BASELINE.md`._
