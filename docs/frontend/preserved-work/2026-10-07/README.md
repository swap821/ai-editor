# Preserved frontend work — 2026-10-07

This directory preserves older Codex-associated frontend work for PR #432. It is **not active product code**, a deployment, a completed-feature claim or acceptance evidence. The normal `frontend/` diff contains the current implementation. Superseded or unfinished alternatives here must be reviewed before integration, not applied wholesale.

## Contents

- Final nothing-left sweep: **13 snapshots / 262 diff headers / 52 current Codex branch tips**, all changed source paths accounted for. See `completeness-audit.json`. It adds formerly omitted tool/notebook paths, the older V1 draft/ignored author progress, and V2 staged index (`stagedDiffLines`). Original trees remain unchanged; these are recoverable alternatives, not all activated product code.
- `codex-other-history.bundle` preserves the seven additional Codex branch tips: 29 historical commits beyond master, 74,769 bytes, all nine prerequisites on master. Counts overlap the original bundle; do not add them as unique work. SHA-256: `6B5D77F1033F57C509F06C69E685D7EE7BDA0C6D3BB3DD51365BE7A6E8CCF143`.
- Fresh unchanged final frontend source: **1,351 passed / 209 files**, coverage-enabled, exit0. Complete report: `docs/frontend/verification/2026-10-07/frontend-final-source.xml`; all209 source tests are tracked in published72f18b23. This is not green CI or production acceptance.
- The original publication below contained12snapshots/253headers/45selected refs; the current manifest and audit supersede those counts without changing the original history bundle.

- Twelve `*.patch.json` snapshots contain 253 per-file diff headers across older dirty worktrees and the separate reference lab. They capture frontend source, frontend plans and builder continuity; runtime output and the inherited bandit budget are excluded.
- `manifest.json` records source paths, source commits and 45 selected local frontend branch tips. Branch identity is not authorship: inspect commit authors. The historical mirror has mixed underlying Claude history and later shared drafts and is explicitly not exclusively Codex-authored.
- `codex-history.bundle` preserves 101 branch commits beyond master on 31 tips, including 33 beyond all current remotes. It excludes only master's history so recovery does not depend on old remote branches remaining undeleted. Already-published branch commits and genuine other-contributor commits carried by these branches retain their original authorship. It is a verified 416,505-byte Git bundle, not 45 separately pushed branches.

## Reading and recovery

Each JSON snapshot stores the patch as `diffLines`. Joining these lines with LF (`\n`) reconstructs a conventional Git diff, including whitespace inside source lines. The JSON wrapper keeps those source characters intact without adding trailing whitespace to the archive itself. Read the source commit and snapshot together; new-file patches are included. Ordinary Git line-ending conversion warnings are not part of the diff and were removed.

The 14 prerequisite commits are listed in `manifest.json` and all belong to the recorded master history. Verify the bundle in a full clone containing that history before importing refs into a **separate recovery tree**. Do not restore over current work or Claude's checkout. A shallow clone or a clone containing only a newer branch's shallow tip is insufficient.

The external reference-lab snapshot is preserved here for inspection, not pushed as a change to that repository and not ported into the product. Original branches, worktrees and immutable preservation stashes remain untouched. These files receive no completion credit toward the seven-phase living-being vision.
