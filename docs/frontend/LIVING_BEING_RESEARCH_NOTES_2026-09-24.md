# Living-being blueprint: audit provenance

Date: 2026-09-24. Planning/research record; not a new product test result.

## Baseline and observations

- GitHub reports #362 merged at 05:53:42 UTC on 2026-09-24. Fetched master: `4782cfa356ad23015bf090f7a671b74967a373f8`, containing #362/#364/#363.
- Source inspected in isolated #362 and blueprint worktrees. `git diff 32952865 origin/master --stat -- frontend` returned no changes.
- The operator checkout was read for initial recall only; unrelated local state was preserved.
- Count: tracked TS/TSX/JS/JSX/CSS in `frontend/src`, using PowerShell `Measure-Object -Line`; tests identified by `.test.`/`.spec.`. 250 non-test files / 44,681 nonblank lines; 175 test files / 15,110 nonblank lines. Comments included; not a code target.
- Inspected the existing production build on temporary loopback port 5190. Desktop screenshot showed the brain/spine beside a separate conversation rail, mode/status controls and Stop. Luminous internal forms soften fine detail; this is a visual judgment of that capture.
- Accessibility tree reported `Operational picture unavailable` with reachable-service copy. No task was sent, session enrolled, approval granted or backend stop invoked during planning.
- CSS viewport 390×844 reported document width 390, request input height 44px, canvas approximately 390.4×354.2 at y=110. Capture was scaled and not credited as detailed mobile visual proof. Viewport override reset.
- No new unit suite, build, backend suite, hardware soak or human test was run for documentation-only work. The 953-test result is historical branch evidence.

## Source findings

| Finding | Source |
| --- | --- |
| Actual body consumes older effective phase/shared uniforms; timed ambient waves remain | `frontend/src/superbrain/core/CortexEngine.tsx` |
| New physical projection drives additional geometry | `frontend/src/workbench/SuperbrainReactiveEffects.jsx` |
| Worker states currently project to ordinal slots | `frontend/src/livingMirror/being/physicalSnapshot.ts` |
| Two differently shaped BeingPresentation families coexist | `beingPresentation.ts`, `beingScenePresentation.ts`, `semanticKernel.ts`, `useBeingPresentation.ts`; import search |
| Current quality behavior differs from older comments | `frontend/src/superbrain/components/QualityTierProvider.tsx` |
| Bootstrap rejects a manifest; check requires omitted ignored source | `frontend/tools/sync-superbrain.mjs`, `frontend/superbrain-source.json` |
| Production same-origin gateway already intended | `frontend/src/config.js`, `frontend/vite.config.js` |
| Inspected Vite response policy blocks microphone | `frontend/vite.config.js`; actual deployed gateway not audited |
| Counters read in useFrame need complete-composer validation | Reactive effects and `observability/frontendMetrics.ts`; Three.js info documentation |

## Historical proof reviewed, not rerun

Current resume and [physical implementation](GAGOS_PHYSICAL_EMBODIMENT_IMPLEMENTATION.md) record authenticated chat, approval, write, development verification and bounded fixture soaks. The [worker probe](evidence/gagos-physical-live-worker-boundary.md) returned `strategy_unavailable`; the [verifier record](evidence/gagos-physical-live-verification.md) distinguishes unavailable normal containers from the explicit development runner. The [human protocol](GAGOS_2030_HUMAN_VALIDATION_PROTOCOL.md) remains a separate gate. The blueprint does not repeat the stale claim that all authenticated evidence is absent.

## Research and limits

Primary sources checked: R3F frame-loop/scaling guidance, Three.js migration/statistics, MDN WebGL/mobile APIs, W3C motion/target size, web.dev Web Vitals and an original animation paper. Links and applied decisions are in the blueprint.

The motion-design skill informed interruption, staging, restrained frequent controls and reduced motion. Generic cookbook claims were not treated as GPU guarantees; primary documentation and measurements govern implementation decisions.

Ruflo memory search was invoked during recall. Disk code/current repository evidence remained the authority. No swarm was started and no private runtime payload was sent to a research service.
