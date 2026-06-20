# GAGOS Orchestration — The Locked Model (Vision Spec)

> **Source of truth:** the operator's brainstorm prototype
> `.superpowers/brainstorm/64579-1781546418/content/synthesis-v2.html`
> ("Corrected · the locked orchestration model"), reaffirmed 2026-06-21.
>
> **Operator decisions (2026-06-21):**
> 1. On multi-tab work the being **docks smaller + up** (mini-brain) so the center is free.
> 2. **Single-tab materialization keeps the lateral-peer look** (poster panel 4) — unchanged.
>
> **Sacred:** palette + textures untouched — luminance / geometry / motion / scale / position only.
> Points mode (`?ui=superbrain&being=points`). Test on **:5173**.

---

## 1. The model in one sentence

When the being orchestrates multiple work tabs, the **spine runs dead-center**, the **being docks small at the top**, the **attended tab sits dead-center + forward** (largest, brightest, the spine feeding live data *down into it*), and **every other tab waits** — nerve-tethered, small, dim, idling — **parked in the four corners**, ready to be pulled to center when the being turns to it.

This supersedes the current build's orchestration (focus off to the right, waiting tabs strung down both sides of the spine).

## 2. States

### 2a. Single tab — "a tab is born" (materialization) — UNCHANGED
The being stays **full size**; the one tab grows as a **lateral peer beside the cortex** (poster panel 4), fed by a thin umbilical nerve, facing the camera. This is the *birth* of a tab, not orchestration. The operator approved this look — leave it.

### 2b. Orchestration — 2+ active work tabs — THE LOCKED MODEL
- **Being docks.** ≥2 active work tabs → the being eases **smaller + up** toward the top (`deriveBrainPresenceLayout` `'docked'` mode: lower `mainBrainScale`, raised position) so the center is open. At rest / 0–1 tabs → full size, centered. Eased (damped), never a snap.
- **Spine.** Dead-center, straight down (already true). **Live data beads flow DOWN the spine into the focused tab** — the "fed by the spine" read (reuse the existing bead/flow + `uStatePulse`).
- **Focused (attended) tab.** **Dead-center + forward** (toward the camera), **largest + brightest**, faces the camera (already implemented), with the focus-pulse edge. Exactly one focus at a time.
- **Waiting tabs.** Parked in the **four corners** (TL, TR, BL, BR), **small + dim + slightly recessed**, gently **idling** (slow bob), each **tethered by a nerve from the spine**, with a soft **"waiting" pulse** dot. They are connected but at rest.
- **Depth hierarchy.** Focus = front + bright + large; waiting = back + dim + small.

### 2c. Attention switch
When the being "turns to" a waiting tab, that tab animates **corner → dead-center-forward** (becomes the focus) and the previous focus **recedes to a corner**. v1: a quick eased lerp; richer choreography later.

## 3. Composition rules
- Never more than **one** focused tab.
- Up to **4** prominent waiting tabs (the corners). Beyond 4 → deeper/smaller corner stacks; **`log()` if capped** (no silent truncation).
- The docked being must **never overlap** the focused tab.
- **Nerves root at the SPINE**, not the cortex (anchor-to-spine law holds). The focus nerve is the brightest (carries live data); waiting nerves are dim.
- Tabs keep their filepath labels for now (the prototype's media/docs/browser/terminal *typing* is a later nicety, see Open Questions).

## 4. Implementation sketch (files)
- **`lib/livingWorkspaceLayout.ts`** — points branches, keyed on the **active work-tab count** (new input field):
  - count ≤ 1 + focused → **lateral peer** (unchanged).
  - count ≥ 2 + focused → **center-forward** (x≈0, large, strong +z toward camera).
  - count ≥ 2 + waiting → **4-corner slot by index** (TL/TR/BL/BR), small + dim; 5th+ recess deeper.
- **`components/canvas/SuperbrainScene.tsx`** — drive **brain docking** in points mode: active work-tab count ≥ 2 → ease `BrainModel` scale down + position up (`deriveBrainPresenceLayout('docked')`); restore at rest.
- **`lib/tabStore.ts` / `components/canvas/MaterializationLayer.tsx`** — expose the **active work-tab count** to the layout + scene.
- **`components/canvas/MaterializedTab.tsx`** — waiting tabs get the dim + idling "waiting pulse"; focus keeps center-forward + camera-facing; emphasize the spine→focus data bead while working.

## 5. Sacred + constraints
- No hue / region-color / texture / GLB changes — luminance / geometry / motion / scale / position only.
- Mesh path untouched; everything gated behind points mode.
- Hold the P6 ~60fps budget (corner tabs are small + cheap; docking only changes a transform).

## 6. Verification (live, :5173 &being=points)
- 1 tab → being full-size, tab as lateral peer (regression check — unchanged).
- 3–4 tabs → **being docks small + up**, focus **center-forward**, others in the **4 corners** dim/idling, nerves from the spine to each; orbit to confirm the focus stays readable + every nerve stays connected.
- 209+ superbrain tests green; layout tests updated for the new branches.

## 7. Open questions
- **Attention-switch animation** (corner → center): v1 quick eased lerp vs a richer pull-forward choreography? (default: quick lerp.)
- **Tab typing** (media / docs / browser / terminal labels + icons, per the prototype): adopt now or later? (default: later — keep filepath labels.)
- **Reconciliation with VARIANT H poster panel 5** (tabs seated along the spine): the operator's locked model (corners + center-forward) **wins**; the poster panel was concept art, this prototype is the head.
