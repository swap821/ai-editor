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
#: Only pytest on a single training_ground/ or lab/ .py file may run as an
#: approved command -- either spelling (`python -m pytest` / bare `pytest`),
#: optional quotes, and a single VERBOSITY flag (`-q` or `-v`) allowed on
#: either side of the target. Nothing else (no pip, no shell, no paths outside
#: the sandbox, no other flags).
#:
#: `-v` was added 2026-08-18 by operator decision, after a golden cohort on
#: gemini-3.7-flash scored 1/5 where FOUR of the five failures were this
#: allowlist refusing `pytest -v training_ground/<file>.py`. The model was
#: doing the right thing -- running the tests it had just written -- and a
#: model that prefers `-v` scored 2.7x worse than one that prefers `-q`, which
#: measured the regex rather than the system.
#:
#: This is deliberately the SMALLEST possible widening. `-v` changes pytest
#: output verbosity and nothing else: same binary, same single-file target,
#: same sandbox constraint. It does not admit a new command, a new path, or a
#: new capability. Everything the old pattern refused, this one still refuses
#: -- pinned by tests/test_probe_allowlist.py, which asserts the refusals
#: rather than only the permissions.
#:
#: NOT widened: `--collect-only` (present in one of the four rejections),
#: `-k`, `-x`, `--tb`, multiple files, or any flag taking a value. Those are
#: separate decisions and none of them are needed to run a test.
ALLOWED_CMD_RE = re.compile(
    r"^(?:python -m )?pytest(?: -[qv])?(?: \"?(?:training_ground|lab)[/\][A-Za-z0-9_\-]+\.py\"?)?(?: -[qv])?$"
)
