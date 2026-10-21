# D12: practice, fact-check and re-admission

*Dated evidence, written 2026-10-21. Do not rewrite: add a superseded banner if
a later run changes the picture. The design is `PAYOFF_PREREGISTRATION.md`, D12
and its 2026-10-18 amendments. The judged runs are reported separately in
`PAYOFF_D12_RESULT.md`.*

## What D12 changed, and why

Phase 8 found no payoff: ON equalled PLACEBO (64 vs 64), only 11 lessons were
admitted, and the student wrote its own lessons, 4 of 19 of them false. D12 puts
a strong cloud teacher (`global.moonshotai.kimi-k3`) in charge of every lesson,
practises on 156 targets the judged lists never use, then fact-checks every
lesson before the operator re-admits the true ones.

## Practice: two streams over the same 156-target ranking

Both streams use teacher Kimi K3 with `--retries 2`, harness `a694eb84`, and the
operator's IAM key in AWS account 424123861008 / us-east-1 (the 2026-10-18
amendment).

| | Cloud stream | Local stream |
|---|---|---|
| Student | `qwen.qwen3-coder-30b-a3b-v1:0` (Bedrock) | `ollama.qwen3.5:9b@nothink` (the operator's laptop) |
| Targets | 136 (the first 20 went to the teacher pilot) | 156 |
| Ran | 2026-10-18 15:53 to 2026-10-19 17:55 IST, interrupted once (below) | 2026-10-19 21:43 to 2026-10-21 03:29 IST, 29.3 h |
| Student earned | 59 (34 on the first try) | 56, 36% (35 on the first try, 21 after a teacher lesson) |
| Teacher earned | 62 | 86 |
| Nobody earned | 15 | 14 |
| Store | `C:\d12out\practice-cloud\w0.db` | `C:\d12out\practice-local\w0.db` |

**What went wrong, and what was done.**
- **Cloud.** A Windows Update reboot killed the run at target 90. It resumed at offset 109 into the same store, with a fresh corpus. The interrupted target's mutation was restored first.
- **Local, first attempt.** It was stopped after 2 targets, at the operator's request, so he could restart the laptop. Its output is kept as `invalid-stopped-for-restart-practice-local`. The run then restarted from the beginning with a fresh corpus.
- **Local student timeouts.** 89 of 380 attempts (23%) hit the pre-registered 420 s limit. This is measured, not a fault:
  - the 9B model is 76% on the CPU (the RTX 3050 has 4 GB);
  - it writes about 7 tokens/s, and that rate held from the first target to the last (Ollama's own log);
  - long answers on hard targets ran out of time;
  - Ollama's log shows no prompt was truncated (prompts are 350 to 510 tokens).
- **Teacher refusals.** In 5 cases the teacher's passing fix proved nothing about the code under test. Each lesson stayed pending ("guesses stay pending"), as D11 intends.

## Fact-check: every verified lesson, both streams

All 168 lessons the two stores hold as `verified` were checked against the
function they are about, at the practice corpus commit `a694eb84`. About 45 were
confirmed by running the function; the rest by reading it. Every verdict, with
its reason, is in `docs/learning/d12_factcheck.json`. One checker did this
(Claude); the reasons are written so the operator can spot-check any of them.

| Label | Local | Cloud | Both |
|---|---|---|---|
| true and specific | 65 of 87 (75%) | 41 of 81 (51%) | **106 (63%)** |
| partly true (the example holds; a general claim, a field name or an order is wrong) | 9 | 11 | 20 |
| false | 4 | 5 | **9 (5%)** |
| about the test (patch targets, mock call shapes, which stand-in a test may pass) | 5 | 19 | 24 |
| scanner artefact | 4 | 5 | 9 |

**Compared with D11**, whose student wrote its own lessons: run 1 had 13 of 32
verified lessons false; run 2 had 4 of 19 false. With the teacher writing, 9 of
168 are false (5%), and 106 are true and specific (Phase 8 had 11 in all).

**The "about the test" rule.** A lesson is labelled `about_test` when its point is
the test's own scaffolding, even when it is true. The cloud stream wrote many
more of these (19 against 5).

**A defect the fact-check found: the secret scanner corrupts lessons.** The
frozen secret scanner redacted ordinary identifiers that look high-entropy:
- `required_inputs_present`
- `InstitutionalSkillAdapter`
- `verification_strength`, which became a hex digest
- `API_TOKEN`, truncated to `API_`

The redacted names reached the failing tests and the lesson text, so the model
learned lessons about the redaction (`[SENSITIVE: …]`), not about the code. All
9 such lessons were excluded. The scanner sits under `aios/security/`, which is
frozen, so a fix there is a proposal for the operator, not an agent's change.

## Re-admission (2026-10-21)

- **The recommended set.** Only the 106 `true_specific` lessons were recommended, never `partly_true`, `about_test`, `scanner_artefact` or `false`.
- **Backup.** Before anything was written, the live store was backed up to `C:\d12out\live_aios_memory_backup_20261021_pre_d12_import.db` (integrity check `ok`).
- **Import.** `tools/import_practice_lessons.py` dry-ran clean: no duplicates against the live store or between the two streams. It then imported the lessons, unsigned:
  - local lessons as ids 122–186;
  - cloud lessons as ids 187–227.
- **Re-admission.** The operator re-admitted ids 122–227 himself with `tools/readmit_learning.py --apply`, signed with his live learning key under his principal (`operator:e2f262a7…`).
- **Census.** The production recall gate now admits **117** of his lessons: the 11 from Phase 8 plus the 106. The census reports `recallable lessons=117/140`; the other 23 older lessons remain unsigned and refused.

## Still not shown

Practice cannot show that lessons help: a retry after a lesson may succeed
without it. A student win after a lesson (21 local) is not evidence of payoff.
The judged runs, OFF / ON / PLACEBO on 150 frozen targets the practice never
touched, are the only test. Their result is in `PAYOFF_D12_RESULT.md`.
