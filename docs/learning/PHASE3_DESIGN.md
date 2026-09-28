# Phase 3 design: provenance, signing and derivation

*Drafted 2026-09-28, for the plan "the learning loop, held to the cage's
standard" (threats T1, T2, T11, T14). It covers standard property 2 ("provenance,
signed asymmetrically") and property 9's derivation graph. The retrieval-time
guard and the prompt envelope are Phase 4; they rest on this.*

## What is true today (read from the code, 2026-09-28)

- **Every recall into a prompt goes through `MemoryAuthority`.** Phase 2 made the
  authority the chokepoint:
  - `recall_lessons` / `recall_verified_lessons` (lessons, A2)
  - `recall_skills` (skills, A3)
  - `facts_search` / `facts_neighbors` (facts, A6)
  - `self_model` (A7)
  - `recall` (semantic memory, A1)

  The turn pipeline calls these (`aios/api/turn_pipeline.py`: `_recall_lessons`,
  `_recall_skills`, `_recall_facts`, `_recall_self_model`, `_recall_memory`).
  Reflexes (A4) are gated by the skill library since slice 2.4c-B.
- **Every learning write goes through the authority too:** `lesson_record`,
  `record_lesson_or_increment`, `promote_lesson`, `record_skill_attempt`,
  `facts_add_fact`, `facts_strengthen_or_propose`, `semantic` promotion, and
  the cerebellum's compile.
- **No learning row carries a principal, a session, a model, a run, an approver
  or a signature.** The one exception is the skill library's
  `SkillRecord.provenance`, a free-form dict that nothing signs.
- **One signing pattern already exists:** `aios/security/audit_logger.py`, which
  is frozen and is reused by pattern, not modified. It takes an Ed25519 seed from
  a volatile environment variable and pins the public key outside the database,
  because a database cannot be its own trust root.

## The design

### 3.1 One provenance record, signed

A new module, `aios/memory/provenance.py`, defines:

- `Provenance`, which records:
  - `table`, `row_id` and `content_sha256`: the hash of the row's
    recall-relevant fields, including its status
  - `source_kind`: `live`, `harness` or `synthetic`
  - `principal`, `session_id`, `run_id` and `model`
  - `evidence_ref` and `approver`: null unless a human approved
  - `transition`: `created`, `promoted` or `readmitted`
  - `parents`: derivation ids
  - `created_at`
- **The signed bytes** are the SHA-256 of the canonical JSON of the record
  (sorted keys, no whitespace). The signature is Ed25519, stored with a key id
  (the first 16 hex characters of the public key's SHA-256).
- **Per-source keys.** Private seeds come only from volatile environment
  variables: `AIOS_LEARNING_KEY_LIVE`, `AIOS_LEARNING_KEY_HARNESS` and
  `AIOS_LEARNING_KEY_SYNTHETIC`. A process signs as the source whose key it
  holds.
  - **Key separation is the enforcement, not a flag.** The backend holds only
    the live key. A harness tool holds only the harness key, so it cannot mint
    a live row even if it tries.
- **Pinned public keys** live in a committed file,
  `.aios/state/LEARNING_PUBLIC_KEYS.json` (kind → hex). The operator adds them
  (see "Operator steps").
- **No key, no signature.** With no seed, the row is written unsigned. An
  unsigned row is never recalled (3.4), so learning without a key is inert, and
  the doctor says so. Nothing generates an ephemeral key: the audit logger's
  graceful degradation is exactly what this must not copy.

### 3.2 Where the records live

There is one append-only side table per database, rather than columns on every
table:

- **`aios_memory.db`:**
  `learning_provenance(id, row_table, row_id, content_sha256, provenance_json,
  key_id, signature, created_at)`
- **`aios_operational_state.db`:** the same table, for `institutional_skills`,
  keyed by `skill_id@version`.

The reasons:
- one verifier for all channels;
- no migration of seven legacy table shapes;
- a record is never updated, only superseded by a newer one for the same row.

A state change that recall depends on appends a new signed record: a lesson
`pending → verified`, a fact `proposed → active`, a skill activation. The
verifier requires the row's CURRENT content and status to hash to the newest
record. A database-level edit of a lesson's text, or a flip of its status, then
fails verification (T11).

### 3.3 Derivations

`learning_derivations(child_table, child_id, parent_table, parent_id, relation,
created_at)` is append-only:

- trajectory → lesson (reflection)
- lesson → promotion (evidence)
- arc → library skill
- skill → reflex

Phase 6's cascade revocation walks it. Phase 3 only writes it.

### 3.4 Verify on read: refuse, never warn

`MemoryAuthority`'s recall methods pass every row through one function,
`admits(row, context)`. A row is admitted only if all of these hold:

1. its newest provenance record's signature verifies under a **pinned** key;
2. that key's kind is allowed in the context: a live turn admits only `live`,
   and a harness context admits `harness` too;
3. its current content and status hash to that record.

Anything else is dropped. The drop is counted, and journalled once per row as
`refused_unverified`. Nothing falls back to "include with a warning header":
Phase 0b already showed that a header is advice, not a boundary.

### 3.5 Legacy rows are quarantined, never backfill-signed

About 106 lessons, 232 chat rows, the facts, 74 library skills and the
reflexes have no real provenance. Signing them now would forge history, so
they stay unsigned and are therefore never recalled. They are re-admitted in
one of two ways:

- **Re-earned** under the authority (a new, signed row).
- **Operator review:** an operator-run tool, `tools/readmit_learning.py`, dry
  run by default. It shows each row and, on the operator's `--apply`, appends a
  `readmitted` record signed with the live key, with `approver: operator`.
  The key is in the operator's environment only.

**Consequence, stated before building:** after 3.4 lands, recall is quiet until
rows are re-earned or re-admitted. Utility is measured immediately after
(conformance, and a payoff calibration subset) and reported, not assumed.

## Slices (each its own PR, each with a test that fails without it)

| Slice | Content | Live behaviour change |
|---|---|---|
| **3a** | `provenance.py`; the side and derivation tables; signer and verifier, with keys from the environment and pinned public keys; refusals; tests with ephemeral **synthetic** keys | none |
| **3b** | Writes attach signed provenance: lessons, semantic memory, facts, library skills, reflex compile, curriculum; derivations written | rows gain records (unsigned without a key) |
| **3c** | `admits()` on every recall channel; the doctor line; the RT-13 tamper mission re-run | **recall quiet until re-earned or re-admitted** |
| **3d** | `tools/readmit_learning.py` (operator-run) and `tools/learning_keys.py pubkey` (prints only a public key) | none until the operator runs them |

Then **Phase 4**, which rests on 3c's verdicts:

- the envelope;
- principal scoping;
- provenance on the approval surface.

## 3b as built (2026-09-28)

- **Where records are attached: the authority's adapters**, not the authority
  (organ 18's entrypoint). Each adapter owns its channel's fields, so the same
  digest function serves the writer now and the verifier in 3c.
- **Channels covered:**
  - lessons (`mistake_pool`): created, recurred, promoted;
  - semantic memory: recorded (chat and consolidation), promoted;
  - facts: created, reconciled, approved (with the approver).
- **Skills and reflexes follow** once slice 2.4c-B (#412) has landed, because
  both files change there.
- **What each digest covers** (`aios/application/memory/provenance_policy.py`):
  everything recall shows or filters on, status included.
  - A fact's `confidence` is deliberately **not** covered. Auto-extraction
    bumps it every chat turn without naming the fact, and it changes ranking
    only. Covering it would make every approved fact's record stale by the
    next turn.
- **A record that cannot be appended never breaks the write.** The row is
  unsigned, so it is never recalled. The stop is the exception, and re-raises.
- **No laundering: a new state of an existing row is signed only if the state
  it extends verifies** (`ProvenanceWriter.attest_transition`). Found while
  building 3b. `record_or_increment` matches an existing lesson by
  (task, error type) and KEEPS its text. So a lesson written straight into the
  database would have been signed the first time a genuine same-type failure
  recurred onto it, or a real success promoted it. The same held for a semantic
  memory repeated into an injected row.
  - Each store now has one method that finds the row a write will touch
    (`recurrence_candidate`, `duplicate_of`). The write and the adapter's
    pre-read both use it.
  - The adapter captures that row's digest before the write, and the writer
    signs the transition only if the row's newest record verifies over that
    digest under a pinned key.
  - Anything else is appended unsigned and counted (`unsigned_transitions`):
    an injected row, a row edited after signing, a race, or no pinned keys.
  - A fact that names a human approver is the exception: that approval is the
    act being signed. A fact with no approver is never recalled, and stays
    unsigned.
- **Harness children never hold a learning key.** The learning red-team's
  child environment sets every `AIOS_LEARNING_KEY_*` to empty. Empty, not
  absent: the child loads the repository's `.env`, and `load_dotenv` fills only
  what is absent.
- **Residual, stated.** A harness that drives the LIVE backend over HTTP (the
  learning-loop prover) writes through the backend's authority, so its rows
  are signed `live`. That is the same as any user's turn. Keeping one
  principal's rows from another is Phase 4's principal scoping, not signing.

## 3c-1 as built (2026-09-28)

- **Gated channels.** Lessons (the task's pending lessons, the cross-task
  verified lessons, and the self-model's recurring cautions) and semantic
  recall now admit a row only if its newest record verifies under a pinned
  LIVE key, over its current digest (`RecallGate`). They are gated in the
  adapters, with the digest functions the writer signs, so there is one
  derivation. Everything else is refused and counted by reason.
- **Over-fetch.** A gated read fetches three candidates per slot, so refused
  rows cannot quietly shrink recall.
- **Facts are 3c-2.** Their reads serve both the prompt and consolidation,
  and the weighted traversal returns edges without row ids.
- **Keys in tests and in the reel.**
  - The test session gets its own live key, pinned in a session file
    (`tests/conftest.py`), so rows the suite learns are recalled as in
    production.
  - Each red-team mission child gets a throwaway live key pinned in its own
    root, never the operator's.
  - The reel seeds poisoned lessons through the adapters, as reflection does,
    so they are signed. Without that, those missions would "hold" for a
    reason that is not the threat's.
  - RT-13 (a raw database insert) may call a hold only when the gate REFUSED
    something; absence alone is "not reached".
- **Tests on synthetic hits.** CRAG and formatting tests feed search results
  with no database rows. They switch the semantic gate off by name
  (`tests/recall_fixtures.py`); what they measure is downstream of it.
- **The reel on this tree.**
  - **RT-13 went from breached to held, by `learning_signature`.** The row was
    refused as unsigned.
  - **RT-03 and RT-16 still breach, correctly.** The same poisoned lesson,
    learned through the authority, is signed and recalled. That is their
    positive control, and the target of Phase 4's envelope.
  - The rest are unchanged.
- **Deferred.**
  - The doctor's signing line: `doctor.py` is an entrypoint of organs 53
    and 54.
  - The payoff ON arm recalling through the same gate: deviation D8, before
    Phase 8.

## Operator steps (needed before 3c changes live behaviour)

1. Generate a 32-byte seed per source kind **in your own terminal**. The agent
   never sees a private key. Put them in your environment or `.env` as
   `AIOS_LEARNING_KEY_LIVE` (and `_HARNESS`).
2. Run `python tools/learning_keys.py pubkey`. It prints only public keys; commit
   them to `.aios/state/LEARNING_PUBLIC_KEYS.json`.
3. After 3c: re-admit what you want recalled with
   `tools/readmit_learning.py`, or let the loop re-earn it.

## What this does not claim

- **Signing proves origin, not safety.** A fully provenanced lesson can still be
  wrong: that is T13, Phase 6's quarantine rule.
- **It does not stop a model acting on admitted content.** That is Phase 4's
  envelope and Phase 5's reflex authority. RT-19 showed that strong models act
  on a verified poisoned lesson, and signing does not change what a *live-signed*
  lesson says.
