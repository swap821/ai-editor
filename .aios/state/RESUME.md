# AI-OS Builder Resume

**Current goal:** Implement the GAGOS living-being frontend blueprint in official `frontend/`, equally capable on desktop and mobile, preserving truthful backend behavior and evidence gates.

**Current branch/worktree:** `codex/gagos-living-being-keyboard-safe`, `C:/Users/kumar/.codex/worktrees/gagos-living-being-live-audit`, based on `975b9fb9119f20824ad0414b4ba05a7186636c32` (LB-05 source checkpoint). This is separate from the original v2 tree, whose staged LB-04 sheet and memory edit must remain untouched. Codex holds the builder lease for `gagos-2030-living-being-mobile-keyboard-20260924`.

**Last completed + verified:** Added mobile composer VisualViewport tracking with app-root-aware occlusion, blur/unmount cleanup, pinch-zoom/button-focus exclusions, and short-viewport sizing. A red regression reproduced the 520px minimum-height/short-landscape mismatch; correction is verified. Focused suite **7/7**; full frontend **175 files / 962 tests**; TypeScript; build (**4,317 modules**); `test:port` **14/14**; lint **0 errors / 123 warnings**; changed-file lint and whitespace checks passed. `port:check` stops because this worktree lacks the ignored authoring-lab `components/QualityTierProvider.tsx`; no port-check pass is claimed.

**Current ticket:** UX-04 keyboard-aware composer implementation slice is ready for local commit/review. It is not physical mobile acceptance. LB-04 art direction and LB-05 truth states still need operator visual review; no browser or human visual sign-off is recorded.

**Accepted completion:** **3/100** (INT-01 only). UX-04 remains **0/5, blocked**: Android 17 and iOS 27 are OS targets only; both physical phone models remain TBD. Desktop-class hardware, named browser/GPU, human usability evidence and live WorkerFoundry integration remain unverified.

**Next single action:** Operator reviews the local keyboard-safe branch diff; then select exact Android/iPhone models before claiming or scheduling physical UX-04 acceptance.

**Open approvals / blockers:** Exact physical handset models are TBD; no real keyboard/browser/touch/safe-area run. Operator review of LB-04/LB-05 and desktop-class selection remain open. No visual acceptance is claimed. `port:check` is unavailable in this worktree until the ignored authoring lab is present.

**Active files:** `frontend/src/livingMirror/keyboardViewport.ts`, `livingMirror.css`, `frontend/src/superbrain/SuperbrainApp.jsx` and its renderer fallback tests; acceptance ledger, execution pack, CEO log, this resume and experiences. Original v2 staged edits remain outside this worktree and excluded.

**Notes not yet promoted:** Automated viewport tests do not model actual mobile browser viewport/keyboard policy. VirtualKeyboard API remains unused; VisualViewport path needs named-device validation. Keep managed `superbrain/` source ownership intact; this slice changes only product-safe shell files.

**Do not repeat:** Never edit the main checkout or original v2 worktree; acquire/refresh this branch's lease before further edits. Do not infer visual/device acceptance from tests/build. Keep geometry/textures and the art proposal pending operator approval. The authoring lab has no npm scripts; test through official `frontend/`. Keep this branch local unless publication is freshly requested.
