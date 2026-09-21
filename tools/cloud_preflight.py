#!/usr/bin/env python3
"""Ask each configured cloud provider one question, and report only the verdict.

WHY THIS EXISTS SEPARATELY
--------------------------
A provider that is configured is not a provider that answers. Keys expire, free
tiers throttle, model ids get renamed, and an endpoint that 401s looks exactly
like a model that is bad at the task once the result reaches a scoreboard. This
asks each one the cheapest possible question first, so a later run's score is a
statement about the model rather than about its credentials.

It also runs as its OWN PROCESS on purpose. Provider config is read at import
time in several places in this codebase, so probing one provider and then
another inside a single interpreter measures whichever won the import race.

SECRETS
-------
Never printed, never written, never logged. Key material is read from the file
the operator names, passed to the client in memory, and reported only as a
length. The one transformation applied is stripping ``<`` ``>`` from values:
this repository has been bitten before by a key stored as ``<nvapi-...>``, where
the placeholder brackets were copied in with the secret and every call 401'd
while the endpoint looked healthy.

    python tools/cloud_preflight.py --env-file frontend/nvdia/.env
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: One question with a short, checkable answer. A provider that cannot do this
#: cannot write a pytest file, and finding that out costs a few tokens.
PROBE = "Reply with exactly one word: READY"

_CHILD = r"""
import json, os, sys, time
sys.path.insert(0, %(root)r)
from aios.core.openai_compat import OpenAICompatClient
started = time.monotonic()
try:
    client = OpenAICompatClient(
        model=os.environ["AIOS_OPENAI_MODEL"],
        api_key=os.environ["AIOS_OPENAI_API_KEY"],
        base_url=os.environ["AIOS_OPENAI_BASE_URL"],
    )
    reply = client.complete(%(probe)r)
    print(json.dumps({
        "ok": True,
        "seconds": round(time.monotonic() - started, 1),
        "reply": (reply or "")[:120],
    }))
except Exception as exc:
    print(json.dumps({
        "ok": False,
        "seconds": round(time.monotonic() - started, 1),
        "error": type(exc).__name__ + ": " + str(exc)[:240],
    }))
"""


def parse_stanzas(path: Path) -> list[dict[str, str]]:
    """Every provider block in *path*, in file order.

    The file holds several alternatives under the SAME variable names, so a
    plain dotenv load keeps only the last. Splitting on repetition of
    ``AIOS_OPENAI_BASE_URL`` recovers all of them, which is the difference
    between probing one provider and probing four.
    """
    stanzas: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Placeholder brackets copied in with the secret: a real, previously
        # observed failure that presents as a 401 from a healthy endpoint.
        value = value.strip().strip("<>").strip()
        if key == "AIOS_OPENAI_BASE_URL" and current.get("AIOS_OPENAI_BASE_URL"):
            stanzas.append(current)
            current = {}
        current[key] = value
    if current:
        stanzas.append(current)
    return [s for s in stanzas if s.get("AIOS_OPENAI_MODEL")]


def probe(stanza: dict[str, str], *, timeout: int) -> dict:
    env = dict(**{k: v for k, v in stanza.items() if k.startswith("AIOS_OPENAI_")})
    child = _CHILD % {"root": str(REPO_ROOT), "probe": PROBE}
    result = subprocess.run(
        [sys.executable, "-c", child],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**dict(**_base_env()), **env},
    )
    line = (result.stdout or "").strip().splitlines()
    try:
        return json.loads(line[-1]) if line else {"ok": False, "error": "no output"}
    except json.JSONDecodeError:
        return {"ok": False, "error": (result.stderr or result.stdout)[-240:]}


def _base_env() -> dict[str, str]:
    import os

    # Pass the ambient environment minus anything that would let the child pick
    # up a DIFFERENT provider than the one under test.
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("AIOS_OPENAI_", "AIOS_BEDROCK_", "AWS_"))
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args(argv)

    if not args.env_file.is_file():
        print(f"no such file: {args.env_file}")
        return 1

    stanzas = parse_stanzas(args.env_file)
    print(f"{len(stanzas)} provider block(s) in {args.env_file}\n")

    usable: list[str] = []
    for stanza in stanzas:
        model = stanza.get("AIOS_OPENAI_MODEL", "?")
        base = stanza.get("AIOS_OPENAI_BASE_URL", "?")
        keylen = len(stanza.get("AIOS_OPENAI_API_KEY", ""))
        print(f"  {model:<38} {base}")
        print(f"  {'':<38} key: {keylen} chars", end="  ")
        try:
            verdict = probe(stanza, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            verdict = {"ok": False, "error": f"timed out after {args.timeout}s"}
        if verdict.get("ok"):
            usable.append(f"openai.{model}")
            print(f"-> OK ({verdict['seconds']}s) reply={verdict['reply']!r}")
        else:
            print(f"-> FAIL {verdict.get('error', '')[:150]}")
        print()

    print(f"{len(usable)} usable: {', '.join(usable) or '(none)'}")
    return 0 if usable else 1


if __name__ == "__main__":
    raise SystemExit(main())
