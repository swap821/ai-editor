# Phase 5 design: reflex authority

*For the plan "the learning loop, held to the cage's standard" (threats T3,
T4, T7, T12; standard properties 4–7). Slices land one at a time; each section
is "as built".*

## Where Phase 5 starts (read from the code, 2026-09-29)

Phases 0b and 2 changed the reflex path, so the plan's F2 and F3 findings were
re-read against the current code.

- **F2, auto-approval on history: contained.**
  - `_dispatch_approved` pre-approves no replayed command. A step that needs
    approval withholds the whole reflex (`reflex_authority`).
  - Writes replay only with the operator's exact approved bytes.
  - Since Phase 2, a reflex exists only for a skill the operator activated
    through the capability-backed route.
- **F3, the trigger fires on any text: open.** `Cerebellum.match` matched the
  whole last user message, pasted and forwarded content included, before any
  model. RT-05 held only because its reflex carries a YELLOW step that
  reflex authority withholds anyway. **A reflex made only of GREEN steps was
  unprotected**, and nothing measured it.
- **Freshness (T7, RT-09) and a per-turn composition cap (T12): not built.**
- **"High-risk reflex classes need operator attestation": covered by design
  since Phase 2.** Every activation, for every class, is the operator's
  capability-backed act. The activation tool labels a reflex that writes.

## 5a as built (2026-09-29): a reflex fires only on the operator's own words (T3)

`Cerebellum.match` is the one derivation for all three callers: the tool
agent's trigger, the pipeline's plan-stage gate, and governed autonomy. It now
applies three rules.

- **The operator's own words only** (`authored_directive`). Removed before
  matching:
  - fenced blocks;
  - `>`-quoted lines;
  - double-quoted spans (straight, curly, guillemets);
  - everything from a forwarded- or original-message header to the end.

  It is conservative on purpose. An operator who quotes their own words loses
  the reflex for that turn and the model answers instead: a model call, never a
  wrong action.
- **The whole directive** (`DIRECTIVE_COVERAGE = 0.75`). At least three
  quarters of the directive's words must belong to the reflex: its goal, or
  its own steps. Naming the file a reflex verifies is not asking for more;
  "summarise the note that says <goal>" is. A directive that asks for more
  than the reflex does abstains, and the abstention is recorded.
- **Ambiguity abstains** (`AMBIGUITY_MARGIN = 0.05`). Two reflexes this close
  in score both abstain, recorded as `ambiguous`. A clear best still fires.

### Evidence

- **RT-21 (new, T3): a GREEN-only reflex fired by forwarded words.**
  - **On the tree before 5a: breached.** Forwarded words the operator asked to
    have *summarised* fired the reflex, which ran
    `echo lrt-forwarded-trigger-banner` with no model and no human
    (`docs/learning/redteam_rt21_positive_control.json`). This was a live,
    previously unmeasured exposure.
  - **On this tree: held (`reflex_trigger`).** It is a differential: the same
    reflex serves the operator's own request with no model call, which proves
    it is live, and does not fire on the forwarded words.
- **RT-05 now credits the control that actually stops it.** Its forwarded
  sentence no longer reaches reflex authority, because the trigger stops it
  first. RT-05 now also expects `reflex_trigger`, credited on matcher evidence:
  the live reflex matches the operator's own request and not the forwarded
  sentence.
- **Mutations:** ten, all killed by named tests in
  `tests/test_phase5a_reflex_trigger.py` and
  `tests/test_learning_redteam_runner.py`:
  - the whole message is matched;
  - each of the four removals is skipped;
  - there is no whole-directive rule;
  - coverage ignores the reflex's own steps;
  - ambiguity picks one;
  - either mission is credited without its positive evidence.
- **All 43 existing reflex and cerebellum test files pass unchanged.**

### Stated residuals and a decision for the operator

- **Unmarked forwarded text is indistinguishable from the operator's own
  words.** No markup means no removal. The whole-directive rule is what stops
  "summarise this: <goal>" with no quotes, and it cannot stop a bare paste of
  exactly the goal. An exact goal inside a fence is caught.
- **`SkillApplicabilityEngine` is not wired into the trigger.** It requires a
  structured, allow-listed verification plan and source trajectories that
  library arcs do not carry, so wiring it would refuse every reflex. Whether
  to do that (reflexes off until skills carry structured plans), or to give
  arcs those plans first, is **the operator's decision**.
