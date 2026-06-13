# NERVOUS_SYSTEM_REDESIGN.md

> Design-lead close-out of the superbrain manufacturing form. Theme (sacred): **an autonomous AI-OS superbrain travelling constant into the deep-vast knowledgeable infinite space** — a living mind voyaging, never frozen.

---

## 0. The corrected mental model — the nerves are the CONTROL BUS

The single thing the first manufacturing attempt got wrong: it treated the nervous system as **decoration around the brain**, so it felt free to hide the panels the nerves plug into and stand up a separate editor below. That is backwards.

**The nervous system IS how the mind controls the screen.** Verified in code, not asserted:

- `NervousSystem.tsx:204-205` hardcodes `leftTargetX = -4.8` / `rightTargetX = 4.8`; the three wire bundles literally **terminate on UI ports** — left port entry `(-4.8,-1.7,0)` (line 292), right port entry `(4.8,-1.5,0)` (line 307), and the spinal bundle "Plug into TOP of chat box" at `(0,-2.6,1.5)` (line 321, with the comment on line 321).
- Those ports are **real panels embedded in the 3D scene**: `SuperbrainHUD.tsx:1046` `<Html position={[-4.8,-1.7,0]}>` and `:1097` `<Html position={[4.8,-1.5,0]}>`, each with inner `transform: translate(-50%,-100%)` so the panel's bottom-center lands exactly on the wire tip. The author comment at `SuperbrainHUD.tsx:1040-1044` spells out the trick: **omit drei's `transform` prop** so the panel is a flat DOM element pinned to the 3D projection of the point (pixel-perfect, cheap), then manually anchor it to the wire.
- The wires carry **live cognition**, not animation timers. The fragment shader (`NervousSystem.tsx:38-83`) runs three channels: a flowing **DATA PACKET** per wire (`fract(vUv.x*4.0 - uTime*vSpeed + vPhase)`, line 63-64,71); **uBurst** brightening `finalColor *= (1.0 + uBurst)` on cognition (line 73); and **uHold** quieting `finalColor *= mix(1.0, 0.3, uHold)` when the mind defers for approval (line 75).
- The transport is the **cognitionBus** (`lib/cognitionBus.ts`, a module-singleton pub/sub) — both the 3D scene and the DOM HUD subscribe to the SAME stream, which is exactly why they read as one organism. uBurst is driven from `burst.current.intensity` via the module-level `WIRE_BURST_UNIFORM` (`NervousSystem.tsx:86,193`); uHold is the shared `SCENE_UNIFORMS.uHold` leaf (`:183`). `aiosAdapter.ts:110-117` already publishes `{type:'agent-dispatch', detail:'tool engaged: <tool>'}` on **every real tool call**.

So: **every tool — present or future — is a PORT on the nervous system, and the brain commands it by an event travelling a nerve.** A write surges the wires; an approval quiets them; the packet is the command in transit.

### What went wrong (the severing — `?ui=shell`)

`manufacturing.css:21-29` sets `.command-bar / .left-console / .right-console / .terminal-log / .core-readout` to `display:none !important`. **Those are the exact panels the nerves plug into.** The wires still render (canon, untouched) — but now into *invisible dead ports*. Then `SuperbrainShell.jsx:46-66` mounts `<Workbench>` / `<CommandLine>` / `<BuildFeed>` **OUTSIDE** `<WorkspaceCanvas>` — a plain-DOM editor below the band, in a different rendering layer the 3D nerves cannot reach. The control bus was cut from its tools and left dangling. **That is precisely why it reads lifeless and wrong.**

The redesign's one job: **reconnect the nervous system to the work surfaces** so a write travels the nerve and lights the tool it lands on.

---

## 1. The technical crux (the constraint that picks the winner)

The nerves are `TubeGeometry` **inside** the WebGL canvas; their endpoints are **hardcoded 3D coords** that only align with panels rendered at those same projected points. A plain-DOM panel outside the canvas cannot have a real 3D nerve enter it — different layers. There are exactly three honest ways to bridge:

| Bridge | What it is | Canon risk | Side |
|---|---|---|---|
| **(a) Re-tenant the canon ports** | Mount the editor/preview as new in-scene `<Html>` at the **existing** `-4.8 / +4.8` / spinal points, copying the no-`transform` + `translate(-50%,-100%)` anchor. Unchanged nerves plug straight in. | **Zero** — nerves & shader untouched | Mostly product; needs **one tiny lab seam** (see §3) |
| **(b) Re-route the nerves** | Edit `NervousSystem.tsx` endpoints / add a 4th bundle so wires aim at new surfaces. | **High** — canon geometry change → FIDELITY laws (re-tag, re-golden, his-browser parity) | **Lab + `npm run port`** |
| **(c) Faux-nerve overlay** | Keep canon nerves untouched; draw SVG/canvas replica tendrils from the band into DOM panels, synced to the same bus. | None to canon, but **replica ≠ real shader** (fidelity "matched", not identical) | 100% product |

**Hard constraints check (a design that violates these cannot ship):**
1. *Fidelity sacred* — only (a) and (c) keep the 3D scene + nerve geometry/shaders byte-identical. (b) edits canon → triggers the full FIDELITY gate. **All three are shippable; (b) is the only one that needs the re-golden gate.**
2. *Port-clobber* — everything in `frontend/src/superbrain/` is overwritten by `npm run port`. New product files are safe; editing `NervousSystem.tsx`/`SuperbrainHUD.tsx`/`WorkspaceCanvas.tsx` is a **lab** change.
3. *One canvas* — `WorkspaceCanvas.tsx:207` mounts exactly one `<Canvas>`. Work surfaces must dock **into** it (in-scene `<Html>`) or **overlay** it (faux nerves) — never spawn a second.
4. *Hardcoded endpoints* — `(-4.8/-1.7)`, `(+4.8/-1.5)`, `(0,-2.6,1.5)`, frozen to Z≈8.5 / 45° FOV / 16:9 (`tabX=4.82`, `:174`). Docking must **preserve the camera framing** or the plug separates.
5. *GPU* — 16GB laptop + local inference + Monaco + a preview iframe, on top of the cortex Voronoi (single heaviest shader) + PostFX fullscreen pass.

---

## 2. Scored comparison

Scale 1–5 (5 = best). Weighted on the operator's six judging axes.

| # | Architecture | (a) Control-bus truth | (b) Theme + canon fidelity | (c) Product-first feasibility | (d) Functional wiring | (e) GPU on 16GB | (f) Future-port extensibility | **Weighted** |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **1** | **THE EMBEDDED FORGE** (re-tenant canon ports; surfaces hang off the existing nerves) | **5** | **5** | **4.5** | 5 | 4 | 4 | **★ 4.7** |
| 2 | TOOL-PORT BUS (same re-tenant, framed as a declarative port rack) | 5 | 5 | 4.5 | 5 | 4 | **5** | **4.7** |
| 3 | FULL IN-SCENE CONTINUUM (Route A now, optional Route B lab re-route) | 5 | 4.5 | 4 | 5 | **3** | 4.5 | 4.4 |
| 4 | FORGE OF FOUR NERVES (lab re-route + a new 4th nerve, up front) | 5 | 4 | 3 | 5 | 4 | **5** | 4.2 |
| 5 | SYNAPSE BRIDGE (product-side faux-nerve overlay to DOM panels) | 4 | 3.5 | **5** | 4 | **5** | 4 | 4.2 |

**Read of the field.** Architectures 1, 2, 3 are the *same core idea* — re-tenant the canon ports with the real work surfaces inside the one canvas — differing only in framing (1 = literal forge, 2 = extensible rack, 3 = bold full-screen continuum that escalates to a lab re-route). They tie at the top because they are the **only paths where the REAL nerves plug into the REAL Monaco/preview with zero canon risk**. #4 is the cleanest *geometric* truth but pays the canon-change tax on day one. #5 is the safest GPU/zero-lab fallback but ships a **replica** of the sacred wires — acceptable as a stopgap, never byte-canon.

**Recommendation: #1 THE EMBEDDED FORGE, built as a declarative port rack (folding in #2's framing) so future tools are first-class, with #3's Route-B lab re-route held as an explicit later phase.** This wins the operator's insight outright: the nerves literally control the tools, nothing is faked, and it ships almost entirely product-side.

---

## 3. RECOMMENDED — THE EMBEDDED FORGE (port-rack framing)

### Concept
The brain voyages above, **smaller but still travelling** (CSS stage-scale only — the canon scene, Float bob, sway, breath all live). Its two real peripheral nerve bundles drop down and plug into the **editor** (left port, x=-4.8) and the **preview** (right port, x=+4.8); the spinal cord plugs into the **command line** (bottom-center rendezvous). The work surfaces are **new product `<Html>` panels mounted at the exact world-points the unchanged nerves already terminate on**, inside the one canvas. A write surges the wires (real `uBurst`), the packet streaks down the cable that feeds the touched surface, and the panel that received it flashes. An approval quiets the whole organism. Every tool is a **declarative port descriptor** so a future tool (terminal, test-runner, graph) is one more row on the bus.

### Mock

```
┌──────────────────────────────────────────────────────────────┐
│  FIDELITY · SKY:VOYAGE · SURFACE:WEB        ◦ Supervised      │  ← kept canon .topbar (free)
│                                                                │
│                      .·:·.   ((( BRAIN )))   .·:·.            │  ← docked voyage, SACRED,
│                    aura · cortex · 3 canon nerves            │    unchanged, still travelling
│            left   ╱  packets↓                  ╲  right       │
│           nerve  ╱   (real wires)     packets↓  ╲ nerve       │
│      (45 wires) ╱                                ╲(45 wires)  │
│  ┌────────────┴────────────┐      ┌──────────────┴─────────┐ │
│  │ PORT 01·EDITOR write_file│      │ PORT 02·PREVIEW render  │ │  ← NEW in-scene <Html>
│  │  MONACO  ⚡flares on write│      │ ● ● ● live iframe       │ │    AT canon ports
│  └─────────────────────────┘      └────────────────────────┘ │    -4.8 / +4.8
│         plug @ -4.8 ──┘            └── plug @ +4.8           │   (bottom-center = plug)
│                       ╲  spinal (35 wires) ↓  ╱              │
│  [PORT LEDGER]  ┌──────────────────────────────────┐         │
│  01 EDITOR ●    │ PORT 03 · DIRECT THE SUPERMIND  ▸ │ ░glow░  │  ← spinal rendezvous,
│  02 PREVW  ●    └──────────────────────────────────┘         │    ::after wire-glow kept
│  03 CMD    ●  · · cosmos continues · the infinite · [Voyage] │
│  + ADD PORT ▱                                                 │
└──────────────────────────────────────────────────────────────┘
   idle: packets trickle to every port (bus powered)
   write: burst races the nerve + the landed port ⚡flares
   approval: ALL wires dim to 0.3, breath freezes — the mind holds
```

### A refinement of the assigned wording (flagged honestly)
The brief says `<Html transform>`. The canon consoles **deliberately omit** drei's `transform` prop (`SuperbrainHUD.tsx:1040-1044`) to skip R3F matrix scaling and stay pixel-perfect + cheap. For Monaco (its own DOM + web workers) and an iframe, **non-`transform` is both more faithful AND far cheaper** (literal `transform` wraps the surface in a per-frame CSS3D matrix). So the build uses the canon **projection-pinned + `translate(-50%,-100%)`** pattern, not literal `<Html transform>`. The surfaces still sit AT the canon ports and the nerves still plug in unchanged — this is a refinement of the wording, not a violation of its spirit. **If the operator specifically wants the CSS3D-transform look, that is a different, costlier build — his call.**

### Phased build plan (product-side first; lab step flagged explicitly)

**Phase 0 — canon baseline (FIDELITY law).** Before any visual change: confirm the canon tag, capture before-goldens of home (`?ui=superbrain`) in HIS browser. No code yet. *(Per the sacred UI laws and prior practice; the brain scene won't change, but the docked composition is a visual change.)*

**Phase 1 — STOP THE SEVERING (pure product CSS, zero risk).** Replace `manufacturing.css`'s blanket `display:none` (lines 21-29) with **relocation**, not deletion. The nerves must never render into dead ports. This alone restores the "one organism" read even before the editor lands. *Product-only — `manufacturing.css` is a product file.*

**Phase 2 — THE ONE HONEST LAB SEAM (geometry-neutral, ~3 lines, no re-golden).** To put a NEW `<Html>` **inside** the single canvas, we'd have to edit `WorkspaceCanvas.tsx` — but it is **ported** (clobbered by `npm run port`). So we cannot add the sibling product-side. The clean fix: in the **lab** (`GAG demo/gag-orchestrator/src/components/canvas/WorkspaceCanvas.tsx`), add a `children` prop and render `{children}` inside `<Canvas>` — **one prop, renders nothing by itself, touches NO geometry/shader** — then `npm run port` **once**. Thereafter all forge panels are product children passed into the canvas.
   - **Why this is honest, not a loophole:** it is a real lab edit, named as such. But it adds nothing visible, so it does **not** trigger the nerve/scene re-golden (only a sanity check that the canon render is byte-identical with `children=null`). This is the *minimum* lab touch the embedded path needs.
   - **If the operator refuses ANY lab edit:** fall back to Architecture #5 (faux-nerve overlay) — 100% product, lower fidelity, must be his-browser-validated. State this plainly; do not pretend the embedded path is zero-lab.

**Phase 3 — THE PORT RACK (product, the core).** New product file `ForgePorts.jsx` (a.k.a. `PortRack.jsx`), passed as `children` into the canvas:
   - `<Html position={[-4.8,-1.7,0]} zIndexRange={[100,0]}>` wrapping Monaco (`CodeCanvas`), inner `translate(-50%,-100%)` — byte-for-byte the canon anchor. Header: "PORT 01 · EDITOR".
   - `<Html position={[4.8,-1.5,0]}>` wrapping `LivePreview`'s iframe, same anchor. Header: "PORT 02 · PREVIEW".
   - The command line stays a **screen-space DOM** bar positioned where `(0,-2.6,1.5)` projects (the spinal bundle was never a geometric bind — it's a rendezvous). **Reproduce `.command-bar::after`** (the wire-glow gradient, `superbrain.css:1239`) on the new bar, or the brain→bar connection reads dead.
   - Render the ports from a `PORTS` descriptor array `{ id, label, tool, socket }` so a future tool is a one-line push.

**Phase 4 — FUNCTIONAL WIRING (product).** See §6. Subscribe each port to `cognitionBus` for its flare + `uHold` quiet; lift the agent's file writes into the editor's `files` state so the packet's arrival is **truthful**, not theater.

**Phase 5 — VALIDATE (FIDELITY law).** Before/after screenshots in HIS browser; confirm the docked brain is byte-identical to home (same camera, scaled stage), the nerves plug cleanly into the new ports, GPU frame budget holds with Monaco + iframe + local inference running. Tag canon, add goldens for the docked composition.

**Phase 6 (LATER, optional) — Route B lab re-route.** *Only if* the editor/preview need more width or a genuinely new 4th nerve port: re-aim `leftTargetX/rightTargetX` + the spinal control points and/or add one `addWireBundle()` in the **lab** `NervousSystem.tsx`, move the matching `<Html>` positions in the lab `SuperbrainHUD.tsx` **together** (doubled hardcode), `npm run port`, then the **full FIDELITY gate**: re-tag, re-golden, his-browser parity, before/after screenshots. This is a clean, bounded canon change — but it IS a canon change. Hold it until the product-side form is proven and he asks for the wider framing.

### Why this is the recommendation
It is the **most literal embodiment** of the operator's insight and the only path that is both 100%-fidelity AND truly connected with **near-zero lab cost**: the real nerves, the real shader, the real packets plug into the real Monaco and the real preview. The mind doesn't sit *next to* its tools — it is *wired into* them, hanging them off its own nerves in the same infinite space it voyages through. When the agent writes a file, you see the thought leave the cortex, race down the cable, and land glowing on the surface it changed. When it owes the operator an approval, the whole nervous system goes still and waits.

---

## 4. Runners-up (honest notes)

**#2 TOOL-PORT BUS** — identical mechanics to the recommendation; I've **folded its best idea (the declarative port descriptor + visible "+ ADD PORT" ledger) into the recommendation** because extensibility is a stated requirement. As a standalone it ties for first; the only reason it isn't the headline is that "embedded forge" reads more immediately as the manufacturing surface, while the rack framing is the *implementation* underneath. Best when the priority is making "every future tool is a port" legible to the operator at a glance.

**#3 FULL IN-SCENE CONTINUUM** — the bold version: brain *above*, full-width editor/preview *below*, one continuous 3D space with the real scene cosmos as the background (not a CSS cosmos div). Its Route A is exactly the recommendation; its Route B is the §3 Phase-6 lab re-route. **Heaviest GPU** of the field (full-width Monaco + iframe as in-scene `<Html>` reprojecting every frame) — start at Route A and *measure in his browser* before committing to the wide framing. Choose this if he wants the maximal "editing inside the AI's nervous system" feel and accepts the GPU + lab budget.

**#4 FORGE OF FOUR NERVES** — the cleanest *geometric* truth: re-aim the three bundles + add a real 4th "tool-rack" nerve so the wires meet the panels at proper positions, and per-tool dispatch lights real tool-chips. **But it pays the canon-change tax on day one** (re-tag, re-golden, his-browser parity before anything ships) and the new ports must be re-validated against the frozen camera. Pick this only if he wants the genuinely-new fourth nerve and is ready to budget the re-golden up front. Revert is clean (localized control points).

**#5 SYNAPSE BRIDGE** — the **zero-lab, GPU-cheapest** fallback: keep canon nerves untouched, draw product-side SVG/canvas faux tendrils from the band into DOM panels, synced to the same bus (same palette, same `fract()` packet, same burst/hold). **Honest ceiling: it's a replica** — no depth occlusion, no volumetric 115-tube braid, and its root must track the brain's per-frame group sway (`NervousSystem.tsx:166-168`) + Float bob or the tendril lags the real wire root. Reads as "good imitation wires." Use it if he refuses *any* lab edit (even the 3-line seam) or if GPU measurement kills the embedded path — but it must be his-browser-validated and never claimed as byte-canon.

---

## 5. The shared failure mode every candidate must avoid

**Camera-framing drift — the exact bug that killed the shell.** The nerve tips project to fixed pixels tuned for Z≈8.5 / 45° FOV / 16:9 (`tabX=4.82` frozen on purpose, `NervousSystem.tsx:171-174`). Docking the brain into a **shorter band** changes the effective framing, so the tips land at different screen pixels and the panels separate from the plugs. The shell hid the panels but left this mismatch — that is why the nerves dangled.

**Mitigation (all candidates):** do NOT squash into a clipped band. Dock by **uniformly scaling the whole stage** (CSS `transform: scale` on `.sb-brain-stage`, the approach `SuperbrainShell.jsx:37` already reaches for) so projection ratios are **preserved**, OR tune the panel anchors to the docked framing in HIS browser with before/after screenshots. This is the make-or-break detail.

Other shared pitfalls (grounded): never a 2nd canvas (re-runs boot, doubles GPU, cross-wires the module-level `WIRE_BURST_UNIFORM`/`SCENE_UNIFORMS` singletons — safe only because the scene mounts once); never blanket `display:none` a port (relocate or re-provide at the same world-point); keep Monaco in a **static-positioned inner wrapper** so only the lightweight `<Html>` anchor reprojects, not Monaco's layout; **debounce** `LivePreview`'s `key={srcDoc}` remount and **park** the iframe when offscreen; new nerves must mutate `burst.current.intensity` for surge but read `SCENE_UNIFORMS.uHold` for quiet (different sources).

---

## 6. Functional-wiring plan (make the forge DO the work, not mime it)

The agent's REAL actions already flow on `cognitionBus` via `aiosAdapter.ts` — verified: `tool_call → {type:'agent-dispatch', detail:'tool engaged: <tool>'}` (`:110-117`), verify pass/fail → `knowledge-acquired` (`:131-138`), approval-required/-resolved, etc. So the scene side needs **zero new plumbing** — the nerves already surge/quiet on every real turn. The forge only has to (a) consume those events for per-port flares and (b) make the surfaces *truthful*.

1. **Write path (agent → editor):** On a `create_file`/`edit_file`, the product write path (the same place the adapter publishes `tool engaged`) (i) pushes the agent-written content into the editor's `files` state (lift `Workbench.jsx`'s state into the port rack or a small product store) and (ii) the EDITOR port — subscribed to the bus, filtered on its tool name — runs a `.port-glow` flare. Result: the editor tab updates with the agent's code **while** the left nerve surges and the packet lands. *Surfacing the file body cleanly:* `cognitionBus` already supports a structured `data` field — carry `path`/`content` there, or read it via a product backend endpoint. **No lab edit.**
2. **Render path (editor → preview):** `LivePreview` already recomputes `srcDoc` from `files`, so the write flows editor→preview automatically; the right nerve surges on the render dispatch. **Debounced** so the voyage doesn't stutter.
3. **Directive path (command line → brain):** `CommandLine.jsx` already reuses `sendDirective`; `SuperbrainHUD.handleSubmit` publishes `{type:'directive'}` before `onDirective` (`:808`), shoving `burst≥0.6` (`SuperbrainScene.tsx:1052`) — the spinal nerve flares as the directive enters the mind. Same wiring, new bar position.
4. **Approval path (hold):** A `human_required` pause publishes `approval-required` → `uHold` eases 0→1 → wires dim to 0.3, cortex amber dims, breath freezes — **whole organism holds**. The kept `.approval-panel` surfaces the diff; the held write sits visibly un-applied in the editor until he approves (the diff IS the pending edit). Resolve republishes and the forge resumes. **RED-zone stays hard-blocked per his policy regardless of approval.**
5. **Add-a-port (extensibility):** Register a future tool = push `{ id, label, tool:'run_tests', socket:'spinal' }` to `PORTS`. If the socket re-tenants a canon port → **pure product**. If it needs its own coordinate → one `addWireBundle()` in the lab (Phase 6). Either way the bus is the universal control plane — the moment the agent actually invokes `run_tests`, the new port flares on the **real** event.

**The honesty gate (the failure this redesign exists to fix):** if a packet arrives but the editor doesn't actually show the write, the bridge is theater. The visual (nerve surge + flare) and the functional (file-state apply) **must ship together** in Phase 3-4, or "the brain controlling the tool" is a lie.

---

## 7. Honest tradeoffs (the bottom line)

- **The faithful "nerves plug into the real editor/preview" form ships almost entirely product-side.** The *only* unavoidable lab touch for the embedded path is a ~3-line, geometry-neutral `children` slot on `WorkspaceCanvas.tsx` (Phase 2) — named honestly, not hidden. If even that is refused, the faux-nerve overlay (#5) is the 100%-product fallback at a fidelity cost.
- **A lab + `npm run port` is genuinely required only to re-aim the real nerves or add a new physical nerve** (Phase 6 / Architecture #4) — a clean, bounded canon change, but it triggers the full FIDELITY gate (re-tag, re-golden, his-browser parity, before/after screenshots). Hold it until the product form is proven.
- **GPU is the real ceiling, not a hypothetical.** Two heavy DOM surfaces (Monaco + a live iframe) composited over WebGL, atop the cortex Voronoi (heaviest shader) + PostFX + the 115-tube braid, on a 16GB laptop also running local inference. The mitigations (non-`transform` projection-pin, static Monaco wrapper, debounced/parked preview, respect `TIER_DPR`) keep it viable for one editor + one preview — **but it must be measured in his browser, not assumed.** If it stutters, demote the preview to a lighter projection-pinned DOM panel that merely sits at the port.
- **Fidelity is sacred and must be proven, not asserted.** The brain scene + nerve geometry/shaders render byte-identical in every recommended path, but the docked *composition* is a visual change — Phase 0 baseline + Phase 5 before/after in HIS browser are non-negotiable.
- **The recommendation deliberately trades the "bold full-width continuum" (#3 Route B) for safety and speed.** Start at the re-tenant form (real nerves, zero canon risk, near-zero lab), prove it in his browser, and only escalate to a lab nerve re-route if he wants the wider framing — the operator picks.
