# GAGOS keyframe A — the docked work plane

**Status:** First implementation slice in the operator-selected A → B → C sequence. The user selected the sequence, not final visual acceptance of this keyframe. Renderer anatomy, shader, palette and protected textures are unchanged. Operator visual review remains open.

## Intent

When a real workspace has focus, the body yields visual room to one persistent, ordinary DOM work surface. The workspace stays selectable, scrollable and keyboard accessible. On narrow screens it takes the available width, while its lower edge tracks the conversation composer instead of relying on a guessed fixed footer. This is a layout contract, not proof that the system is reasoning or that a backend task is admitted.

## Compact visual system

- Void `#030108`; readable text `#e8e6ee`; conduct cyan `#7bf5fb`; resting attention purple `#b06eff`; verified green `#54f0a0`; approval orange `#ff7e40`.
- Continue using the existing `--lm-surface` neutral, not a new tint. Existing failure color and all semantic state rules remain unchanged. Color always accompanies text/structure; green still requires explicit verification.
- Preserve existing type roles: Outfit for shell headings, Inter for interface/body copy, JetBrains Mono for code and technical evidence. No new face, micro-label system or decorative typography.

## Composition

Desktop target (1440 × 900 CSS pixels; a design review size, not a device claim):

```text
┌─────────────────────────┬──────────────────────────────────────┐
│ body / spine             │ one persistent, readable DOM plane  │
│                          │                                      │
│ real composer + status   │ selected task / file / evidence     │
│                          │ normal scroll, text selection, focus │
└─────────────────────────┴──────────────────────────────────────┘
         ~32%                              ~68%
```

Mobile target (390 × 844 CSS pixels; emulator/browser geometry is not handset acceptance):

```text
┌──────────────────────┐
│ existing human controls│
│ compact visible body  │
├──────────────────────┤
│ one full-width DOM    │
│ work plane; scrolls   │
├──────────────────────┤
│ composer (measured)   │
│ connection / safe area│
└──────────────────────┘
```

On desktop, the current split composition keeps the DOM plane at approximately 68% width. Under the mobile breakpoint, the selected plane is full width. The app measures the actual composer top against the app root and gives the plane a 12px separation; resize, composer-size changes and visual-viewport movement refresh that measurement. This covers wrapped controls and keyboard movement without duplicating workspace or attention state. If measurement is unavailable, existing CSS positioning remains the fallback.

## Motion and truth contract

- A layout change is not animated by this slice. Typing, focus, keyboard navigation, approval and Stop remain immediate.
- The scene's posture continues to come from the canonical semantic/physical presentation path. A focused panel alone is not evidence of model activity, admitted work, verification, memory or connectivity.
- Reduced-motion behavior preserves the same content, focus and controls; no body travel or ambient signal is added here.
- Existing approval and Stop controls remain outside the work plane and under their current authority owners.

## Evidence and open review

- The mobile clearance test uses synthetic DOM rectangles: root bottom 844px and composer top 620px produce 236px clearance; moving the composer to 510px produces 346px. This verifies the layout measurement, not pixel output or device behavior.
- Focused app/dock tests: **11/11**. Full frontend: **177 files / 977 tests passed** with Vitest's fork pool capped at four workers and a 10s test timeout. Typecheck and final production build (**4,318 modules**) passed after the observer type-only correction. Full lint: **0 errors / 123 warnings**; changed-file ESLint, CSS palette guard, protected-texture guard and port tooling tests (**16/16**) passed. `port:check` could not compare because ignored lab source `components/QualityTierProvider.tsx` is absent; no restore was attempted.
- Live visual inspection was performed on the isolated `:5193` local preview at 1280 × 720, with “Recent observations” open. The DOM plane was readable and the existing organism canvas was present. The service reported offline and the operational picture unavailable; this is not an admitted-work journey or a 1440 × 900 review capture.
- No 390 × 844 browser capture, 320px reflow capture, physical Android/iPhone, mobile keyboard, accessibility device, named desktop/GPU, operator visual sign-off or independent review is claimed. Exact phone models remain TBD. This slice earns no acceptance points; the evidence ledger remains 3/100.
- Source/test commit: `63881d882f822d579f2a3dde26ade0dd9452f28b` on `codex/gagos-lb04-a-docked-plane-20260925`, local only.

## Self-critique

This deliberately avoids the generic “brain beside neon cards” treatment: it changes only the relationship between the existing focused DOM surface and the real composer. The next useful review is visual, at both agreed composition sizes, with an actual focused surface and truthful state copy. If the measured mobile plane becomes too short around the keyboard, the answer is a reviewed responsive composition change—not hiding controls or inventing another activity animation.
