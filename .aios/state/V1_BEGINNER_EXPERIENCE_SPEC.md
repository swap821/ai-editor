# V1 Beginner / Expert Experience Specification

**Status:** implementation contract  
**Date:** 2026-09-21

## Default opening

The being introduces itself briefly, then presents one plain request:

> What would you like to get done?

Three invitations are available without requiring AI vocabulary:

- **Ask and understand:** ask a question and see a grounded answer.
- **Make something useful:** describe a small artifact or change.
- **Guide me:** choose a bounded task and follow the next clear step.

Voice is available as an alternate entry. The user can always type instead.

## Beginner rules

- Do not require knowledge of models, providers, swarms, castes, organs, or
  security-zone names.
- Before a risky action, explain what will happen in ordinary language and show
  the exact approval control.
- After an action, distinguish completed, verified, refused, failed, stale, and
  unavailable outcomes.
- Never imply that a spoken confirmation authorized a mutation.
- Preserve active work and approval surfaces when switching views.

## Expert/Mirror rules

The explicit Expert/Mirror switch reveals the existing workbench and adds the
technical explanation layer: current route, privacy boundary, memory evidence,
approval state, verification evidence, runtime state, governance, and journal
continuity.

Expert mode does not gain new authority. It only exposes more measured truth.

## First-ten-minute target

The default funnel is **understand → do → inspect**:

1. The user asks or speaks naturally.
2. GAGOS answers or proposes one bounded next action.
3. The user explicitly approves any risky action.
4. GAGOS reports the result and verification honestly.
5. The user can open Expert/Mirror to inspect the evidence.

Guided tasks and voice remain alternate entry paths into the same funnel rather
than separate product authorities.

## Accessibility and recovery

- Keyboard input remains available when speech is unsupported or denied.
- Voice controls expose listening, interrupted, unavailable, and failed states.
- Mode switching is keyboard reachable and announced.
- Reduced motion keeps all state changes understandable without animation.
- A failed or disconnected turn offers a recoverable next action and never
  fabricates a successful answer.

