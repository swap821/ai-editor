"""Shared helpers for operator-authorized probe / curriculum-evidence drivers.

The allowlist regexes live in ONE module so the curriculum driver, daily-use
probe, and any future evidence runners share the same fail-closed sandbox
policy for file writes and verifier commands.
"""

from __future__ import annotations

import os
import re

from aios.config import API_TOKEN, PROBE_BASE

#: Base URL for the GAGOS HTTP API, configurable via ``AIOS_PROBE_BASE``.
BASE = PROBE_BASE


def probe_headers() -> dict[str, str]:
    """Headers every evidence driver needs to reach a SECURED backend.

    These drivers were written when ``/api/generate`` was open. The API has
    since required "a bearer token or a valid session, exact Origin, and
    session-bound CSRF proof" for any mutation, and nobody re-ran the drivers
    against it -- so organ 44's own production entrypoint could not execute at
    all, and returned a bare 403 before reaching a single model.

    The bearer token is the server-configured ``AIOS_API_TOKEN``. Read from the
    live environment first and only then from the import-time config constant,
    so a driver launched in the same shell as the server picks up the token
    without the import order mattering. Never written to disk here.

    Nothing is weakened: a driver that cannot authenticate is not more secure,
    it is only unable to produce evidence.
    """
    headers = {"Origin": "http://localhost:5173", "Content-Type": "application/json"}
    token = os.environ.get("AIOS_API_TOKEN") or API_TOKEN
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


#: Only bare .py files directly inside training_ground/ or lab/ may be written.
ALLOWED_FILE_RE = re.compile(r"^(?:training_ground|lab)[/\\][A-Za-z0-9_\-]+\.py$")
#: Output-only pytest flags. Each changes what is PRINTED, never what runs:
#:   -q/-qq/-v/-vv  verbosity      --no-header   suppress the header block
#:   --collect-only list, run none  --tb=<style>  traceback format
#:
#: Widened 2026-08-18 by operator decision, twice. First for -v, after a cohort
#: on gemini-3.7-flash scored 1/5 with FOUR of five failures being this regex
#: refusing `pytest -v <file>`. Then for the rest, after the re-run scored 3/5
#: with BOTH remaining failures being `--collect-only` and `--no-header`.
#:
#: The point is not convenience. Every model reaches for different flags --
#: 2.5-pro writes bare `pytest`, 3.7-flash adds -v and --no-header, DeepSeek
#: adds --noconftest -- so a gate that admits one spelling measures pytest
#: HABITS and reports them as capability. Three missions that passed cleanly
#: were scored as failures because of how the model formatted its output.
#:
#: NOT admitted, deliberately: -k and -x (change which tests run), -p (loads
#: arbitrary plugins), --pdb (interactive), --noconftest (changes collection),
#: --rootdir/-c (take a path), multiple files, and anything that is not pytest.
#:
#: Built from NAMED PARTS rather than one long literal. The previous widening
#: was written as a single pattern and lost a backslash: [/\\] became [/\],
#: whose \] escaped the bracket so the class never closed, swallowed the next
#: one and silently admitted `/` -- permitting nested paths the gate had always
#: refused. Sixteen hand-written refusal tests all still passed.
_PYTEST_READ_ONLY_FLAG = r"(?: -(?:[qv]{1,2}|-collect-only|-no-header|-tb=[a-z]+))"
_SANDBOX_TEST_FILE = r"(?: \"?(?:training_ground|lab)[/\\][A-Za-z0-9_\-]+\.py\"?)"
ALLOWED_CMD_RE = re.compile(
    r"^(?:python -m )?pytest"
    + _PYTEST_READ_ONLY_FLAG + "*"
    + _SANDBOX_TEST_FILE + "?"
    + _PYTEST_READ_ONLY_FLAG + "*$"
)
