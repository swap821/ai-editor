"""Credential-shaped paths that are refused INSIDE an allowlisted scope root.

## Why this exists

`scope_lock` answers one question: is this path under a declared scope root?
That is containment, not confidentiality. The moment a scope root is widened to
a real project -- which is exactly what Phase B/F autonomy requires -- a `.env`,
a `.git/config` holding a push token, or a `.aws/credentials` sitting inside that
allowlisted root is fully readable and writable. Nothing stopped it.

Inventory item 2. This is the denylist that runs **in addition to** the scope
check, never instead of it: a path must be both in scope AND not credential-
shaped.

## What was already here, and why it was not enough

A partial list existed -- `agent_bridge._SECRET_MARKERS` -- and was consulted at
exactly one call site, for read tools only. Measured against it before this
module was written:

    .env                     -> caught
    ~/.ssh/id_rsa            -> caught
    .ssh/config              -> MISSED
    .aws/credentials         -> MISSED
    .git/config              -> MISSED
    .docker/config.json      -> MISSED
    .claude/settings.json    -> MISSED
    .netrc                   -> MISSED

The cause is structural, not a missing entry: it matched substrings against the
BASENAME only, so every credential store that identifies itself by its
*directory* was invisible to it. `.aws/credentials` is not a filename problem.

It also guarded no writes at all -- a bridge-authorized agent could not read
`.env` but could overwrite it.

## One derivation, many callers

`is_credential_path` is the single answer. `agent_bridge.looks_secret_bearing`
now delegates here rather than keeping its own weaker copy, and every file
read/write chokepoint calls this same function. Two independently-maintained
answers to "is this credential material?" is the shape that produced the gap
above; `tests/test_credential_denylist.py` enumerates the chokepoints and fails
if a new one appears unguarded.

## Deliberately fail-closed

A false positive costs an operator one renamed file. A false negative ships a
private key to a cloud model. When a name is ambiguous, it is refused.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath

#: Basename globs. Matched case-insensitively against the final path segment.
CREDENTIAL_NAME_PATTERNS: tuple[str, ...] = (
    # Environment / dotfiles that conventionally hold secrets
    ".env",
    ".env.*",
    "*.env",
    ".netrc",
    "_netrc",
    ".npmrc",
    ".pypirc",
    ".dockercfg",
    ".git-credentials",
    ".htpasswd",
    # Private key material
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "*.ppk",
    "*.asc",
    "*.gpg",
    # Cloud / service credential files
    "credentials",
    "credentials.*",
    "*service-account*.json",
    "*.pkcs12",
    "known_hosts",
    "authorized_keys",
)

#: Directory names that make EVERYTHING beneath them credential material,
#: wherever they appear in the path. This is the half the previous basename-only
#: check could not express: `.aws/credentials` is identified by `.aws`, not by
#: the filename `credentials`.
CREDENTIAL_DIR_SEGMENTS: frozenset[str] = frozenset(
    {
        ".ssh",
        ".aws",
        ".azure",
        ".gcloud",
        ".config/gcloud",
        ".gnupg",
        ".docker",
        ".kube",
        ".git",
        ".claude",
        ".codex",
        ".gemini",
        ".anthropic",
        ".openai",
        ".netlify",
        ".vault",
        "secrets",
        ".secrets",
    }
)


def _normalize(path: str | Path) -> PurePosixPath:
    """Lowercased POSIX view of *path*, with `~` and drive noise removed.

    Case folding matters on Windows, where `.ENV` and `.env` name one file.
    """
    text = str(path).replace("\\", "/").strip().lower()
    # Strip a leading `~` or `~user` so `~/.ssh/id_rsa` is segmented properly.
    if text.startswith("~"):
        text = text.split("/", 1)[1] if "/" in text else ""
    return PurePosixPath(text)


def is_credential_path(path: str | Path) -> bool:
    """True when *path* names credential material and must be refused.

    Checked against BOTH the basename and every directory segment, because the
    two failure modes are different: `id_rsa` identifies itself by its name,
    `.aws/credentials` by its parent.
    """
    normalized = _normalize(path)
    parts = normalized.parts
    if not parts:
        return False

    for segment in parts[:-1]:
        if segment in CREDENTIAL_DIR_SEGMENTS:
            return True
    # A directory itself, addressed with no trailing file (e.g. `.ssh`).
    if parts[-1] in CREDENTIAL_DIR_SEGMENTS:
        return True

    name = parts[-1]
    return any(fnmatch.fnmatch(name, pattern) for pattern in CREDENTIAL_NAME_PATTERNS)


def refusal_reason(path: str | Path) -> str:
    """Operator-facing explanation, used verbatim by every caller.

    One wording for one rule: a refusal that reads differently at each chokepoint
    invites the reader to believe they are different rules.
    """
    return (
        f"'{path}' is credential-shaped and is refused even inside an allowlisted "
        "scope root. Scope membership is containment, not permission to read "
        "secrets. If this file genuinely is not credential material, rename it."
    )


__all__ = [
    "CREDENTIAL_DIR_SEGMENTS",
    "CREDENTIAL_NAME_PATTERNS",
    "is_credential_path",
    "refusal_reason",
]
