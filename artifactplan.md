GAGOS · 54-organ green contract

Proof plan: turning implementation into attestation
Six PRs shipped working code and moved the ledger by zero organs. The remaining work is almost entirely verification, not features. This is the order to do it in, and an honest account of what cannot be finished here at all.

Ledger green
38 / 54
Flipped by PR 1–6
0
Authority class missing
45 / 54
Empty live evidence
53 / 54
Green, no tested SHA
12 / 38
Blocker text present
16 / 54
READ FIRST
Two definitions decide the size of everything below
Decision A — is authority_owner a class reference or a label?
45 of 54 organs name a class that does not exist, including 33 of the 38 that are already green. validate_ledger() only string-compares the field against a registry of strings, so the question has never been forced.

Class reference → build 45 real owners, and 33 current greens are wrong and drop to yellow first. The number gets worse before it gets better.
Conceptual label → condition 1 already holds; instead make validate_ledger() resolve the named module or entrypoint. Far cheaper, still real.
Decision B — does live evidence actually gate green?
The contract lists it as condition 10. The ledger's own schema disagrees: requires_live_evidence is false for all 54 organs, and exactly one organ (40) has ever produced any. If condition 10 binds every organ, several can never go green here — see Outside this machine.

ORDER
Why this sequence
The order is dependency, not preference. Phase 0 changes what "done" means for 45 organs, so nothing before it can be trusted. Phase 1 banks evidence already earned, which is free and de-risks the rest. Organ 23 is last by its own definition — its blocker text says it stays non-green until every organ below it is green.

0
S · blocking
Settle the two definitions, in writing
Why first: 45 organs hang on Decision A and 53 on Decision B. Any work started before these is work that may have to be redone or retracted.

Steps
Record both answers in AGENTS.md or the ledger schema docs — a durable rule, not a chat message.
Teach validate_ledger() to enforce whichever reading won, so the field stops being unverifiable.
If Decision A is "class reference", drop the 33 unsupported greens to yellow in the same commit. One honest regression beats a standing overstatement.
Exit criteria
Condition 1 is mechanically checked by CI, and the ledger's status column means the same thing for every organ.
1
S
Bank the evidence already earned
Why here: pure recording, no new code, no new risk — and it produces the first genuine proof PR to use as a template for all the rest.

Steps
Organ 52 proof PR: its live-Docker trace run already passed twice in CI (4 passed, pre- and post-restart) and is sitting unrecorded. Attach the run URL + commit in organ 40's format.
Record last_verified_sha for the 12 green organs that have none, against a commit CI actually verified.
Wire --strict-release into a CI gate. The flag exists in verify_organ_contracts.py and runs in no workflow, so SHAs go stale silently.
Exit criteria
Zero green organs without a tested SHA; organ 52 holds real live evidence; the SHA guard has teeth in CI.
2
L · largest
Give every organ a real owner
Why here: shape is fixed by Decision A. Doing it before Phase 0 risks building 45 classes the answer says were unnecessary.

Steps
Use the three built in PR-5/#169 as the template: the class owns the mechanism, a real route or startup hook invokes it, and the test asserts reachability, not existence.
Work the 16 yellow organs first — they are being touched anyway — then the greens in risk order.
Reject any owner that is a pass-through wrapper. A class that only forwards calls satisfies the checkbox and changes nothing.
Exit criteria
Condition 1 passes for all 54 under CI enforcement, with a caller test per organ.
3
M
Close the per-organ condition gaps
Why here: conditions 3, 4 and 5 are per-organ engineering with two working templates already in the tree.

Steps
Tamper-evidence (condition 4) — copy the organ 42 journal chain or the organ 38 provenance chain. Compute the digest in one function used by both writer and verifier; that mismatch is what broke organ 38's chain originally.
Durable state (condition 3) — the organ 52 rotating handler is the pattern for anything that currently dies with the process.
Fail-safe reporting (condition 5) — report unavailable rather than a plausible zero.
For each of the 16 blocker texts, either close it or rewrite it to state precisely what remains.
Exit criteria
Every organ has a written per-condition verdict; nothing is unverified without a stated reason.
4
M · partly blocked
Produce live evidence where the infrastructure exists
Why here: needs Phase 2–3 landed so the run exercises the finished path — and it is where the hard ceiling sits.

Steps
achievable Docker-backed organs. CI already runs a real container; organs 40 and 52 prove the route.
achievable Anything provable through the API against real SQLite state in CI.
blocked Cloud-provider organs — needs real credentials in CI. Operator-supplied; I am barred from handling secrets.
blocked Local-model organs — needs a live Ollama in CI (a service container or self-hosted runner).
Exit criteria
Every organ either holds live evidence, or records a specific named reason it cannot — never silence, and never a test described as if it were a live run.
5
M · repeated
One proof PR per organ
Why here: this is the step the whole campaign skipped. Six implementation PRs merged yellow, per the plan's own rule — and not one second PR was ever written.

Steps
Re-verify all 12 conditions against the code, not against the ledger's own prose. PR-6 flipped four organs against a commit CI never ran.
Attach evidence, record the tested SHA, then flip — in that order.
Sequence: organ 52 first (already earned), then the other 13 yellow, then re-verify the 33 greens whose condition 1 was never checked.
Exit criteria
Every organ's status survives an adversarial re-read of all 12 conditions.
6
S · capstone
Organ 23 — the release conformance gate
Why last: not a choice. Its own blocker text says it stays non-green until every organ below turns green and the final release proof lands.

Steps
Regenerate the manifest with its script — never by hand. Hand-editing is how it drifted to a rebased-away commit before.
Run the strict release gate over the whole ledger.
Publish the result as either 54/54, or an itemised shortfall naming each organ and the exact condition it fails.
Exit criteria
A release proof that a hostile reader can check without trusting any prose in the ledger.
TARGETS
The 16 yellow organs
Most of these already say, in their own blocker text, that the implementation is finished — "now wires it", "is now resolved". They are waiting on attestation, not code. Two are different: 44 needs real cloud infrastructure, and 23 gates on all the others.

Organ	Name	What actually remains	Phase
52	Observability & Health	Evidence earned and unrecorded — the cheapest real flip available	1
25	Constitutional Kernel	Blocker says implemented and deliberately not flipped; needs owner + evidence	2–5
27	Operator Taste Model	Store wired to production; needs owner + attestation	2–5
28	Project Understanding	Pointer made durable; needs owner + attestation	2–5
29	Correction Lineage	Route now builds typed records; needs owner + attestation	2–5
30	Human-State Interpreter	Digest-mutation bug fixed; needs owner + attestation	2–5
31	Representative Context Compiler	Ledger row was itself stale — re-scope before judging	2–5
32	Universal Intelligence Gateway	Routing real; live evidence likely needs cloud credentials	4–5
33	Model Registry & Passport	Passport projection shipped; needs owner + attestation	2–5
36	Clerk Dispatcher	Dispatcher real; live proof wants a local model	4–5
38	Clerk Provenance	Chain persists in production; needs owner + attestation	2–5
42	Recovery & Resumption	Owner, chain and startup scan landed in #169 — needs evidence + SHA	1–5
46	Constitutional Learning	Owner landed; probes covered; human red-team still absent by design	3–5
53	Installation & Key Authority	Rotation + grace period real; needs owner + attestation	2–5
44	Golden Mission & Endurance	Needs 12 governed missions across two real cloud providers	4 · blocked
23	Release Conformance	Gates on every other organ — cannot move until last	6
LIMITS
Outside this machine
These are capability limits, not effort limits. No amount of work here closes them.

Cloud-provider live evidence. Needs real credentials in CI. You hold them; I am barred from handling secrets and must not put them on disk.
Local-model live evidence. Needs a live Ollama in CI — a service container or self-hosted runner. An infrastructure decision.
Organ 44's golden cohort. 12 governed missions across two real cloud providers. Depends on both items above.
Organ 46's human red-team. The organ's own text says the automated floor is not a substitute. It needs a person.
The green flip itself. By your plan's framing, declaring an organ green is an operator claim about your system.
GUARDRAILS
What must never count as proof
not proof
Its class exists.

not proof
A unit test constructs it directly.

not proof
The ledger has no blocker text.

not proof
The feature renders on screen.

not proof
A commit message says it is complete.

learned here
A commit SHA that CI never ran. PR-6 flipped four organs against one.

The fast route to 54/54 is 45 pass-through classes and evidence prose describing unit tests. That produces a number worth less than the honest 38, and it is the exact failure this ledger exists to catch — most recently in PR-6. Build real, or report yellow.