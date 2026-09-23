# GAGOS 2030 Human Validation Protocol

Status: protocol prepared; no participant evidence has been collected.

This protocol is intentionally human-owned. Automated tests, screenshots, and
agent inspection do not count as participant evidence.

## Purpose

Check whether a non-builder can use the Guided front door without learning
GAGOS internals, while preserving a clear path to Expert/Mirror inspection.

## Participants

Recruit at least three people who did not build or review this renovation.
Record only a participant label (`P1`, `P2`, `P3`), not names or private
content. Obtain consent to observe the session and to record notes. Do not
upload prompts, files, audio, screenshots containing private content, or
telemetry to an external service.

## Session setup

- Use the local installer/pilot environment selected by the operator.
- Test once with the 3D organism available and once with the visual fallback
  if renderer failure can be safely induced by the test owner.
- Have a small disposable project ready; do not use a real private repository.
- Verify the backend/session boundary before asking for any mutation.
- Use a desktop or tablet session plus one 320–375px mobile session across the
  participant set.
- The facilitator must not explain models, workers, providers, organs,
  capabilities, councils, or policy IDs before a participant asks.

## Tasks

Give each participant these tasks in order, using neutral wording:

1. Ask a normal question or ask GAGOS to explain the project.
2. Request a small bounded project change.
3. When permission appears, decide whether to deny it safely.
4. Request another bounded change and approve it once.
5. Identify what happened and whether the result is verified.
6. Stop the system while work is in progress, if a real stop state is
   available; otherwise inspect the stop control without inventing a result.
7. Recover or undo the change only when the UI presents a real backend-owned
   recovery action.
8. Find the explanation for the permission decision and result.
9. Optionally switch to Expert/Mirror and explain what additional information
   is visible and whether it changed authority.

Do not coach a participant toward a correct answer. If a backend truth is
unavailable, record the participant's reaction to the honest unavailable or
unverified state instead of substituting a demo result.

## Observation sheet

For every task, record:

| Field | Notes |
| --- | --- |
| Task / participant | `P1`–`P3`, task number |
| First action | What the participant tried without prompting |
| Hesitation | Where they paused or asked what to do |
| Wrong assumption | What they believed the UI meant |
| Unknown word | Any internal or unexplained term |
| Misclick / recovery | Incorrect action and whether they recovered |
| Safety comprehension | What they thought Allow / Don’t allow / Stop meant |
| Truth comprehension | Whether they distinguished finished from verified |
| Result | Completed, blocked, or unavailable; exact observed UI state |
| Facilitator note | Only factual context, no interpretation disguised as evidence |

## Success criteria

The flow is provisionally understandable when each participant can, without
technical coaching:

- start with the main request field or a starter path;
- explain what a permission request will affect and what denial does;
- distinguish a verified result from finished-but-unverified work;
- find and operate Emergency Stop or accurately explain why it is unavailable;
- locate a safe explanation and, where offered, recovery/undo;
- switch to Expert/Mirror without believing that visibility grants authority.

Any repeated confusion, repeated vocabulary question, or safety misread is a
product bug candidate. Do not average it away.

## Evidence handling

Store a redacted note table with participant labels and dates. Keep raw audio,
private prompts, project files, and screenshots out of the repository. The
implementation report may be updated only with observed counts and direct
quotes that participants explicitly permit; until then it must continue to say
that human validation is pending.
