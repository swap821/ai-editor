# AI‑OS — Independent System Audit

**Date:** 2026‑06‑21 · **Branch:** `feat/living-being-p1` · **Auditor:** Claude (Cowork), at the operator's request
**Scope:** whole repo — `aios/` backend + security spine, `frontend/` (superbrain 3D + classic shell), repo hygiene.
**Method:** read core docs, then three parallel deep‑dives (backend/security, frontend/UX, repo hygiene) with direct file verification.

> Framing: this is honest peer review, the kind AGENTS.md §IX explicitly asks for — naming flawed
> assumptions and hidden debt, including the project's own. Credit is given where the engineering is
> genuinely strong; the rest is the work that remains.

---

## 1. Verdict

This is an unusually disciplined system for a solo build. The security spine is **real engineering, not
theater**: a fail‑closed allowlist gateway, server‑issued single‑use approval grants, a tamper‑evident
audit ledger, and a no‑self‑approval property built *structurally* into the architecture rather than
bolted on as a check. ~14k lines of backend, 569 test functions, fully pinned dependencies.

The honest weakness is everything **around** that core. The repo is a brilliant personal workshop
presented as a product: no CI, a dirty tree on a feature branch, nested git repos, junk files, and more
planning docs (122 `.md`) than code files (142 `.py`). And the default frontend — a genuinely beautiful
3D "voyaging mind" — greets a first‑time visitor with a blank screen, an empty chat box, no welcome, no
guidance, and an accessibility story that is mostly aspirational.

**One sentence:** the hard things are done; the *front door* — onboarding, a single brand, a loading
state, honest fallbacks, CI, a clean tree — is what's missing, and almost none of it is a rewrite.

---

## 2. Intent vs. reality

| Area | Documented intent | Actual state |
|------|-------------------|--------------|
| Security gateway | Deterministic, fail‑closed, allowlist | **True.** Unknown/empty/exception → RED. Solid. |
| Audit ledger | "Blockchain‑grade" tamper‑evidence | Tamper‑*evident*, but preimage has no field delimiter (collisions) + tail‑truncation undetected. Overstated claim. |
| Secret hygiene | "No secret persistence" | Mostly true, but the scanner misses PEM blocks, URL credentials, bare `key=`, short hex — and those reach the ledger in cleartext. |
| Approved execution | Gated + isolated | Gated: yes. Isolated: **only if you opt into Docker.** Default `host` runs on your OS. |
| Frontend (default) | "Easy for anyone… amaze on first sight" | Amazes a dev with a fast GPU; confuses/excludes everyone else. No onboarding, blank first frame, `aria-hidden` hero. |
| Tests | "556 passed" green bar | Plausible (108 files / 569 `def test_`), but **enforced by nothing** — no CI. |
| Branch/commits | "per‑phase on `master`" | HEAD is on `feat/living-being-p1`; ~60 uncommitted files. |

---

## 3. Security loopholes (ranked)

Proposed fixes are in **Appendix A**. Per AGENTS.md §XI the `aios/security/*` spine is **FROZEN** — these
are *proposals for §VIII review*, not changes I applied.

1. **[MED] Secret‑scanner coverage gaps → secrets land in the audit log.**
   `secret_scanner.py` entropy pass only fires at length ≥ 20 (`_ENTROPY_MIN_LEN`, line 20) and entropy
   ≥ 4.0. These slip through entirely and, because `log_action` redacts via the same scanner *before*
   hashing (`audit_logger.py:159`), get written to the ledger in cleartext:
   - PEM headers (`-----BEGIN RSA PRIVATE KEY-----`)
   - URL credentials (`postgres://user:S3cr3tP@ss@host`) — no `password=` prefix, special chars break the entropy token
   - bare `key=deadbeefcafe1234` — `key` isn't in the `ASSIGNED_SECRET` prefix list, and 16 hex chars < 20
   This is the **most actionable** finding. Fix: Appendix A.1.

2. **[MED] Audit hash‑chain preimage has no delimiter.**
   `compute_entry_hash` (`audit_logger.py:119`) is `SHA256(prev||ts||actor||payload||zone)` by bare
   concatenation. Verified: `actor="ab",payload="c"` hashes identically to `actor="a",payload="bc"`. The
   chain stays tamper‑evident for content edits, but the "blockchain‑grade" claim (`audit_logger.py:9-11`)
   overstates it. Fix: length‑prefix the preimage, ideally HMAC with a key held outside the DB (Appendix A.2).
   *Note:* changing the preimage breaks continuity with existing entries — needs a chain‑version bump or
   re‑genesis. This is exactly why it's a §VIII proposal.

3. **[MED] Approved commands run on the host OS by default.**
   `APPROVED_EXECUTION_BACKEND` defaults to `"host"` (`config.py:233`). The executor *honestly documents*
   that host mode is "not an OS/container isolation boundary" (`executor.py:17-23`). The Docker runner is
   excellent (`--network none`, `--cap-drop ALL`, `no-new-privileges`, non‑root, read‑only root) — but
   it's opt‑in. Most users will run host mode. Recommendation: make container the default for
   arbitrary‑code classes, or surface a loud one‑time warning. (Config change — not frozen.)

4. **[LOW] Env‑scrubbing is a name *denylist* → bypassable by naming.**
   `_sanitise_env` (`executor.py:272`) strips vars whose name matches `_STRIPPED_NAMES` /
   `_SECRET_NAME_HINTS`. A credential in `DATABASE_URL`, `GITHUB_PAT`, or `OPENAI_ORG` passes straight
   into approved child processes. Combined with #3, an approved command can read and (via filesystem)
   exfiltrate them. Fix: expand hints, or invert to an allowlist (Appendix A.3).

5. **[LOW] `verify_chain` doesn't detect tail truncation.**
   It walks existing rows only (`audit_logger.py:200`); deleting the last N rows leaves a valid shorter
   chain. Persist an external high‑water mark (signed head hash + entry count) outside the DB.

**Genuinely solid (don't touch):** the gateway ordering (injection→secret→destructive→network→env→escape→
composition→scope→caution→safe), scope lock resolving symlinks + splitting on shell ops before
tokenising, `secrets.compare_digest` for the API token, CORS failing closed on `*`+credentials, no bare
`except:` anywhere (all 76 broad excepts carry `# noqa: BLE001` + rationale), and the self‑apply flow
(snapshot → `git apply --check` → audit‑before‑write → single‑file confinement → gated verify →
auto‑rollback).

---

## 4. Frontend — honest state + beautification roadmap

**This is the section you care about most, so it's the most detailed.**

### What a first‑time user actually experiences at `/`
1. **A blank screen** while the heavy three.js bundle + shaders compile (`Suspense fallback={null}` in
   `main.jsx:40`). Dead air as the first frame. *(Partly fixed this session — see §7.)*
2. The brain fades in with a "GAGOS" wordmark, three status pills, and an **empty chat box** —
   **no welcome, no example prompts, no hint** of what this is or what to type. A beautiful locked room
   with no sign on the door.
3. The polished "GAGOS KERNEL boot" cinematic in `BootSequence.tsx` is **dead code** — never rendered on
   the home route. You built the wow and then unplugged it.
4. If WebGL fails or the backend is down, it doesn't degrade — it renders broken/empty, and boot "facts"
   fall back to **fictional numbers** ("18.23 GB", "2,605 nodes") shown as real status. Your own
   PRODUCT.md says "data must be true"; this violates it.

### Accessibility: aspirational, not real
PRODUCT.md promises WCAG AA, 44px targets, keyboard, reduced‑motion. Reality: the entire hero scene is
`aria-hidden="true"` with **no text alternative and no 2D fallback**; the keyboard‑navigable `RegionPins`
live *inside* that aria‑hidden canvas (so they're hidden too); mic/send buttons are **38px**; and the
always‑on WebGL scene keeps animating under reduced‑motion (the reduced‑motion CSS targets old class
names the home no longer renders). "Easy for anyone" and `aria-hidden` on the whole interface cannot coexist.

### Two design systems that disagree
- `tokens.css` (classic): canvas `#050507`, **blue** `#3b82f6`, Geist/Inter. *This file is excellent —
  OLED ramp, fluid `clamp()` type scale, physics easing, semantic status colors. Keep it as the base.*
- `superbrain.css` (default): void `#030108`, **cyan** `#7bf5fb`, Inter/Outfit/JetBrains.
- Plus the product is called, variously: **AI Orchestrator, AI‑OS, Jarvis, GAGOS, Enterprise, Secure
  Gateway.** A newcomer can't tell what it's named.

### No mobile / responsive story
`GagosChrome.css` has zero breakpoints; the chat is hardcoded `width: min(430px, 40vw)`, absolutely
positioned, and on a phone collides with the centered being while a heavy WebGL scene drains battery.

### Prioritized roadmap (highest impact first)

| # | Fix | Why it matters | Effort |
|---|-----|----------------|--------|
| 1 | **Kill the blank first frame** | The boot moment *is* the wow; right now nobody sees it. | S — *done in part, §7* |
| 2 | **The brain speaks first** | A greeting + 3 clickable starter prompts turns "what is this?" into "whoa." | S |
| 3 | **One name, one palette** | Two palettes/fonts/names read as two half‑finished products. | M |
| 4 | **Honest degradation** | WebGL2 check + `<noscript>` + real 2D fallback; never show fake numbers. | M |
| 5 | **Reachable body** | `aria-label` + keyboard text‑equivalent, 44px targets, truly stop motion on reduce. | M |
| 6 | **Responsive home** | Breakpoints; stack chat below the being on narrow screens; pause RAF when hidden. | M |

Concrete starter‑prompt copy that fits the voice: *"I'm GAGOS — a supervised mind that remembers. Try:
**build a landing page** · **audit my security gates** · **what do you remember about this project?**"*
Implementation sketches for #2/#4 are in **Appendix C** (new product‑safe components, so they don't fight
the `npm run port` overwrite of the ported 3D tree).

The reassuring part: the hard thing (a living being wired to real backend events) is built. What's left is
~200 lines of "front door."

---

## 5. Repo hygiene (ranked)

Commands in **Appendix B**. Deletion is RED in your own model, and token rotation is on your AWS console —
so these are for you to run, not me.

1. **Live AWS Bedrock token in `frontend/.env` (on disk, not committed).** Gitignored and verified *not*
   in history — so it's not a repo leak, but it's a real credential in the wrong folder (Bedrock is
   backend‑only). **Rotate it and move it to backend env.**
2. **Dirty tree + branch drift.** HEAD on `feat/living-being-p1` not `master`; ~60 uncommitted files;
   two paths throwing `Input/output error` (`.claude/skills/ui-ux-pro-max/{data,scripts}` — corrupt FUSE
   entries).
3. **Nested git repos** — `GAG demo/.git` (+ `gag-orchestrator/.git`), `training_ground/.git`, four under
   `codex-design-workspace/`. Gitignored, so contained, but submodule‑shaped landmines.
4. **Committed junk** — `creator.txt` (0 B), `success.txt`, `chat-ui.html`; plus on‑disk debris
   `frontend/120`, `frontend/700)break` (misfired shell redirects), `_sse_capture.txt`, `.fuse_hidden*`.
5. **Doc/scaffolding sprawl** — 122 `.md` vs 142 `.py`; single docs up to 116 KB; competing agent trees
   `.claude/` (125 files), `.aios/` (53), `aios/` (51, the real package), `.agents/`, `.claude-flow`,
   `.superpowers`. The `.aios/` (notebook) vs `aios/` (code) split is genuinely confusing to a newcomer.

**Clean, credit due:** no secrets in tracked code (only the `AKIA…EXAMPLE` placeholder + test
fixtures), no committed DBs/FAISS (gitignore is thorough), `requirements.txt` fully pinned,
`package-lock.json` committed, `.mcp.json` holds no secrets.

---

## 6. What's missing

- **CI** — *added this session* (`.github/workflows/ci.yml`); see §7.
- **A first‑run experience** — the frontend roadmap above.
- **A single product identity** — pick the name (recommend **GAGOS**) and retire the rest.
- **An external trust anchor for the audit ledger** (finding #5).
- **A 2D / no‑WebGL fallback path** for the default UI.
- **A `CONTRIBUTING.md` / onboarding** that explains `.aios` vs `aios` and the lease protocol to a human
  who isn't you.

---

## 7. What changed this session — applied vs. proposed

**Applied (additive, product‑safe, non‑frozen, uncommitted — review and commit yourself):**
- `frontend/index.html` — an **instant boot loader** (a breathing cyan mark + "waking the voyaging
  mind") that paints before the bundle parses and fades out on `load`; plus a `<noscript>` fallback. It
  exposes a `window` event **`gagos:ready`** so the 3D scene can dismiss it precisely when shaders are
  warm (wire‑up sketch in Appendix C.3). Pure CSS, reduced‑motion aware, zero dependency on the ported
  tree — so it survives `npm run port`.
- `.github/workflows/ci.yml` — **CI** running `pytest -q` (windows‑latest, to match your green baseline) +
  frontend `typecheck` / `test` / `build` (ubuntu). Closes the "green is enforced by nothing" gap.

**Proposed only (your review required):**
- Security fixes #1–#5 — **Appendix A** (frozen core → §VIII flow).
- `host` → container default — config, finding #3.
- Repo cleanup + token rotation — **Appendix B**.
- Frontend roadmap #2–#6 — **Appendix C**.

I did **not** commit anything (AGENTS.md: commit only when the operator asks), and `agent_coord.py status`
showed `active_writer: null`, so nothing was clobbered.

---

## Appendix A — proposed security diffs (FROZEN core · §VIII review)

**A.1 — `aios/security/secret_scanner.py`: close the coverage gaps**
```python
# Add to _NAMED_PATTERNS:
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("URL_CREDENTIALS", re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*://[^/\s:@]+:[^/\s:@]+@")),

# Broaden the ASSIGNED_SECRET prefix list (add bare `key`, `access[_-]?key`, `auth`):
    ("ASSIGNED_SECRET", re.compile(
        r"(?:password|passwd|secret|api[_-]?key|access[_-]?key|auth|key|token)\s*[=:]\s*"
        r"['\"]?[A-Za-z0-9\-_]{8,}['\"]?",   # 12 -> 8 also catches short hex keys
        re.IGNORECASE)),
```
*Add a unit test asserting each of the three example payloads now returns `detected=True`.*

**A.2 — `aios/security/audit_logger.py:119`: unambiguous preimage**
```python
def compute_entry_hash(previous_hash, timestamp, actor, payload, zone):
    # Length-prefixed + NUL-delimited: field boundaries are unambiguous, so
    # (actor="ab",payload="c") can no longer collide with (actor="a",payload="bc").
    parts = (previous_hash, timestamp, actor, payload, zone)
    raw = "\x00".join(f"{len(p)}:{p}" for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    # Stronger: hmac.new(key_from_env, raw.encode(), "sha256").hexdigest()
    # so DB-write access alone cannot recompute the chain.
```
*Migration: bump a chain version / re‑genesis; existing entries verify under the old function. This is
the change that most needs human sign‑off.*

**A.3 — `aios/core/executor.py:272`: stop name‑denylist bypass**
```python
# Minimal: extend the hint set.
_SECRET_NAME_HINTS = {*_SECRET_NAME_HINTS,
    "URL", "DSN", "CONN", "PAT", "CREDENTIAL", "AUTH", "PRIVATE", "SIGNING", "SESSION"}

# Stronger (recommended for arbitrary-code classes): invert to an allowlist —
# pass only PATH, HOME, SystemRoot, TEMP/TMP, LANG, LC_*, and an explicit
# per-command extra set; drop everything else.
```

---

## Appendix B — cleanup commands (you run these)

```powershell
# 1. Rotate the Bedrock token in the AWS console, then move it out of frontend/.
#    (Bedrock is backend-only; it has no business in frontend/.env.)
Remove-Item frontend\.env            # after copying the non-secret bits to backend env

# 2. Remove committed junk markers.
git rm --cached creator.txt success.txt chat-ui.html
Remove-Item creator.txt, success.txt, _sse_capture.txt -ErrorAction SilentlyContinue
Remove-Item 'frontend\120', 'frontend\700)break' -ErrorAction SilentlyContinue

# 3. Investigate the corrupt FUSE paths (I/O error on read):
#    .claude\skills\ui-ux-pro-max\data  and  ...\scripts  — re-clone or delete+reinstall the skill.

# 4. Decide the branch story: either rename feat/living-being-p1 -> master path,
#    or update AGENTS.md/README which still claim "master".
```

---

## Appendix C — front‑door follow‑ups (new product‑safe files)

**C.1 — Greeting + starter prompts.** Add a small `WelcomeOverlay.jsx` mounted from `SuperbrainApp.jsx`
(product‑safe per AGENTS.md). Shows once (gate on `localStorage`), 3 clickable prompts that dispatch into
the existing chat input, auto‑dismisses on first user message. No edits to the ported `GagosChrome`.

**C.2 — WebGL2 + backend honesty.** Before mounting the scene, feature‑detect:
```js
const gl = document.createElement('canvas').getContext('webgl2');
if (!gl) renderClassicFallback();   // reuse ?ui=classic shell as the 2D path
```
And in the boot facts: if the backend `/health` call fails, show **"backend offline"**, never the
fictional constants.

**C.3 — Dismiss the boot loader exactly when the scene is ready.** The loader added this session listens
for `gagos:ready`. In the ported scene's "arrival complete" handler (`WorkspaceCanvas` / the inlined
arrival logic), add one line — this is the *only* ported‑tree edit and belongs in the lab + `npm run port`:
```js
window.dispatchEvent(new Event('gagos:ready'));
```
Until then, the loader self‑dismisses on `load` + a 9s safety timeout, so nothing hangs.

---

*End of audit. Nothing here was committed. The two applied files are uncommitted in your working tree for
review.*
