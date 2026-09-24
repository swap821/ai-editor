# GAGOS physical embodiment — human validation packet

Status: prepared for operator-led validation; no participant or operator
sign-off has been collected. This packet is a coordination aid, not evidence.

The original human-owned protocol remains authoritative:
`docs/frontend/GAGOS_2030_HUMAN_VALIDATION_PROTOCOL.md`. Use this packet to
run the same tasks against the current branch without exposing private prompts,
files, names, recordings, or telemetry to the repository or an external
service.

## Required reviewers

- Three people who did not build or review this renovation, labelled `P1`,
  `P2`, and `P3` only.
- At least one participant with low familiarity with AI tools if available.
- One operator review of the sacred palette and texture/GLB canon at the
  agreed browser viewport.
- One screen-reader pass by a human using an installed screen reader. A DOM
  accessibility tree or keyboard-only inspection does not count as a
  screen-reader pass.

## Session safety

- Use the operator-selected local pilot and a disposable project only.
- Do not use a private repository, private prompt, real credentials, or real
  files.
- Do not ask a participant to approve a real mutation unless the operator has
  already confirmed the backend boundary and the target is disposable.
- Record labels, dates, observed UI states, and factual notes only.
- Do not record names, audio, screenshots containing private content, prompts,
  file contents, or telemetry.

## Participant script

Give each participant these tasks in order, without explaining internal GAGOS
terms beforehand:

1. Ask a normal question or ask GAGOS to explain the project.
2. Request a small bounded project change.
3. When permission appears, deny it safely.
4. Request another bounded change and approve it once, only if the operator has
   provided a safe disposable target.
5. Identify what happened and whether the result is verified.
6. Stop the system while work is in progress, or explain accurately why a real
   stop state is unavailable.
7. Recover or undo only when the UI presents a real backend-owned action.
8. Find the explanation for the permission decision and result.
9. Optionally open Expert/Mirror and explain what extra information is visible
   and whether it changed authority.

## Observation sheet

Copy one table per participant. Use exact visible wording where possible.

| Field | P1 | P2 | P3 |
| --- | --- | --- | --- |
| Date / viewport |  |  |  |
| First action |  |  |  |
| Hesitation |  |  |  |
| Wrong assumption |  |  |  |
| Unknown word |  |  |  |
| Misclick / recovery |  |  |  |
| Permission comprehension |  |  |  |
| Finished vs verified comprehension |  |  |  |
| Stop comprehension |  |  |  |
| Refusal comprehension |  |  |  |
| Expert changes perceived authority? |  |  |  |
| Result: completed / blocked / unavailable |  |  |  |
| Factual facilitator note |  |  |  |

Repeated confusion is a product bug candidate. Do not average it away.

## Human screen-reader checklist

Run on the real root route and, if the operator approves, the development-only
gallery. Record the screen reader and browser version, but no user content.

- [ ] Main landmark and page identity are announced.
- [ ] The request field has a meaningful accessible name and instructions.
- [ ] Skip-to-chat is reachable and moves focus to the request field.
- [ ] Guided / Expert-Mirror controls announce their pressed state.
- [ ] Send, voice, and Emergency Stop controls have meaningful names.
- [ ] Emergency Stop details announce their expanded/collapsed state and the
  exposed controls.
- [ ] Quality selection and Reduced motion announce their current values.
- [ ] Major state changes use a useful live announcement without repeating
  decorative telemetry.
- [ ] Approval, refusal, verification pass/fail, stale, stopped, and unavailable
  states are distinguishable without color or 3D motion.
- [ ] Focus remains usable when a workspace or receipt appears.
- [ ] No keyboard or screen-reader path requires 3D interaction.

Screen-reader evidence is complete only when a human records the observed
announcements and any failure. Browser snapshots alone remain supporting DOM
evidence.

## Operator visual sign-off

At the agreed desktop viewport, inspect the sacred palette and texture/GLB
assets in the root product surface and representative physical gallery states.
Record only `pass`, `fail`, or `not run`, with a short factual note.

| Check | Status | Note |
| --- | --- | --- |
| Palette matches operator canon |  |  |
| Texture / GLB assets match operator canon |  |  |
| Body and spine read as one coherent being |  |  |
| Approval visibly dominates machine activity |  |  |
| Refusal stops at the boundary without success treatment |  |  |
| Verification pass differs from unverified completion |  |  |
| Failure / rollback does not settle as success |  |  |
| Stop preserves visibility and human controls |  |  |
| Worker branches read as temporary and bounded |  |  |
| Workspace connection reads as growing from the being |  |  |
| Guided view hides internal vocabulary |  |  |
| Expert view adds inspection without adding authority |  |  |

## Acceptance rule

Do not update the implementation report to claim human validation until all
three participant sheets, the human screen-reader checklist, and the operator
visual sign-off contain dates and factual results. Any repeated confusion,
screen-reader failure, or operator `fail` remains an open finding rather than a
green gate.
