# Proposal: the entropy pass leaves camelCase names alone

**Status: Propose. It awaits the operator's Human Review → Approve.**
- Written 2026-11-14 by the coding agent, at the operator's word ("Plz honestly fix it also").
- `aios/security/secret_scanner.py` is frozen core (AGENTS.md §VIII). Applying any change to it is RED, and the agent cannot apply this; only the operator can.
- Nothing here takes effect by itself. Every number below was measured on `5c530fa2` without writing the frozen file. The rule was evaluated beside the scanner, or patched in memory for one process.

## Observe

**A council goal could not be done, because a name was hidden.**
- On 2026-11-14 the council's goal gt-15f3457c24 asked for five more calls of `deriveTurnMetabolismSnapshot` in `turnMetabolism.test.ts`.
- The scanner's Pass 2 redacts that name: 28 characters, Shannon entropy 4.138 bits per character, over the 4.0 threshold.
- GAGOS's masking therefore showed the writer each of the file's 8 calls as a placeholder, and the answer was refused for repeating one.
- That refusal is fixed outside the frozen core (branch `fix/task-placeholder-repeat`). The writers and reviewers still read `GAGOSMASKQ_0000` where the code says `deriveTurnMetabolismSnapshot`.

**Measured across `frontend/src`, `aios`, `tools` and `scripts`:**
- Pass 2 redacts **143 distinct tokens**.
- **46** of them are camelCase or PascalCase names, occurring 552 times. Examples:
  - `LivingWorkspaceShell`
  - `derivePhysicalSnapshot`
  - `EmergencyStopHardWiringAuthority`
  - `subscribePendingApproval`
- The other 97 are mostly path fragments, kebab-case ids and SCREAMING_SNAKE constants. This proposal leaves them as they are.

**The cause.** Pass 2 has no context gate: any run of 20 or more `[A-Za-z0-9+/\-_]` with entropy of at least 4.0 is redacted. Mixed case raises a name's entropy past the threshold. The precedent proposal (`docs/superpowers/specs/2026-07-03-scanner-path-entropy-proposal.md`) found the same for paths; snake_case mostly stays under it.

## Propose

In Pass 2 only, a token that is wholly a camelCase or PascalCase name is not redacted:
- it consists of letters only;
- its first word is all lowercase or capitalised;
- every following word is one capital, then at least one lowercase letter.

```diff
--- a/aios/security/secret_scanner.py
+++ b/aios/security/secret_scanner.py
@@ (beside _is_filesystem_path)
+#: A camelCase or PascalCase name: letters only, each word after the first one
+#: capital then lowercase. Exempt in Pass 2 only (2026-11-14 proposal):
+#: Pass 1's named formats and Pass 3's context-gated window still apply.
+_CAMEL_CASE_NAME = re.compile(r"[a-z]+(?:[A-Z][a-z]+)+|[A-Z][a-z]+(?:[A-Z][a-z]+)+")
+
+
+def _is_camel_case_name(token: str) -> bool:
+    return _CAMEL_CASE_NAME.fullmatch(token) is not None
@@ Pass 2, _entropy_replace, after the filesystem-path check
             if _is_filesystem_path(token):
                 return token
+            if _is_camel_case_name(token):
+                return token
```

**Unchanged:**
- Pass 1, the named credential formats including `ASSIGNED_SECRET`;
- Pass 3, the sliding window, which redacts only near a secret keyword;
- the threshold, the minimum length and every other token shape.

## Test (measured, read-only)

**Real names (simulated, rule patched in memory).**
- `turnMetabolism.test.ts`: 8 placeholders become 0.
- All 633 frontend files: placeholders fall from 2,279 to 1,965 (14%), and masked files from 375 to 359.

**Random keys, 200,000 of each alphabet, 20 to 48 characters.** Most are redacted today; the question is how many the rule would let through.

| Alphabet | Redacted today | Would be exempted |
|---|---|---|
| base62 | 193,544 | **2** |
| letters only | 189,461 | **249** (0.13%) |
| base64url | 194,107 | **0** |

**Secret shapes, unchanged under the rule:**
- `AKIAIOSFODNN7EXAMPLE`: Pass 1, `AWS_ACCESS_KEY`.
- A `ghp_` token: Pass 1, `GITHUB_TOKEN`.
- `password = CorrectHorseBatteryStapleMountain`: Pass 1, `ASSIGNED_SECRET`.
- The bare passphrase `CorrectHorseBatteryStapleMountain` is not redacted today (its entropy is under 4.0), so the rule changes nothing for it.

**A snake_case rule was measured and is NOT proposed.** It would cover only 9 more names, and it would exempt 86,887 of 132,416 random lowercase-and-underscore strings.

## Risks, honestly

- **A real key made of letters only, shaped exactly like camelCase words,** would no longer be caught by Pass 2. At 0.13% of letters-only keys and about 0.001% of base62 keys, it is rare but not zero. Pass 3 still catches it near a secret keyword.
- **No new evasion channel.** A model told to smuggle a secret out can already spell it as words separated by spaces, which no entropy pass sees. This rule leaves that unchanged.
- **Limits:** the rule fixes no context-gated case. On 2026-11-12, `ownsWorkSurface(writingTab.id, token)` was redacted by Pass 3, next to the word `token`, and stays so. Paths, kebab-case ids and SCREAMING_SNAKE constants are untouched, and so is the privacy filter's own high-entropy pass on routes that hide identifiers.

## To apply (the operator's acts)

1. Apply the diff above to `aios/security/secret_scanner.py`, with a test pinning both directions:
   - the 46 names pass;
   - a letters-only key that is not camelCase-shaped, and every Pass 1 format, are still redacted.
2. Record the §VIII ceremony in the same diff, as `scripts/check_frozen_core.py` requires.
3. The secret scanner is organ 3's entrypoint (AGENTS.md: organs 1-5's entrypoints are the frozen spine), so the spine's evidence must be re-signed. That is his act.
4. After the merge, GAGOS's next hour masks with the new rule. No GAGOS code changes.
