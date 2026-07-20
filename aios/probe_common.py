"""Shared helpers for operator-authorized probe / curriculum-evidence drivers.

The allowlist regexes live in ONE module so the curriculum driver, daily-use
probe, and any future evidence runners share the same fail-closed sandbox
policy for file writes and verifier commands.
"""

from __future__ import annotations

import re

from aios.config import PROBE_BASE

#: Base URL for the GAGOS HTTP API, configurable via ``AIOS_PROBE_BASE``.
BASE = PROBE_BASE

#: Only bare .py files directly inside training_ground/ or lab/ may be written.
ALLOWED_FILE_RE = re.compile(r"^(?:training_ground|lab)[/\\][A-Za-z0-9_\-]+\.py$")
#: Only pytest on a single training_ground/ or lab/ .py file may run as an
#: approved command — either spelling (`python -m pytest` / bare `pytest`),
#: optional quotes, `-q` allowed anywhere. Nothing else (no pip, no shell, no
#: paths outside the sandbox).
ALLOWED_CMD_RE = re.compile(
    r"^(?:python -m )?pytest(?: -q)?(?: \"?(?:training_ground|lab)[/\\][A-Za-z0-9_\-]+\.py\"?)?(?: -q)?$"
)
