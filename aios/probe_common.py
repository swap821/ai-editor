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
#:   -s             show print()   
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
_PYTEST_READ_ONLY_FLAG = r"(?: -(?:[qv]{1,2}|s|-collect-only|-no-header|-tb=[a-z]+))"
#: `-o addopts=` with an EMPTY value, and nothing else.
#:
#: Widened 2026-08-19 by operator decision, for a reason the other widenings did
#: not have: the harness's OWN forced auto-verify runs
#:
#:     python -m pytest -o addopts= "training_ground/test_x.py" -q
#:
#: (`build_auto_verify_command`), and the agent loop shows the model that exact
#: command as the `target` of a step that just succeeded. The model copied the
#: form the loop had demonstrated, and this regex refused it -- terminating the
#: mission. Organ 44 lost a mission per cohort to a command its own harness
#: relies on. Two derivations of "what may run" disagreeing: the same shape as
#: the containment escapes tests/adversarial/test_control_consistency.py exists
#: to catch, here between the verifier and the gate that judges it.
#:
#: `-o` in general is NOT admitted and must not be: it overrides ANY ini option,
#: so `-o addopts=--pdb` would inject an interactive debugger. The lookahead
#: pins the value to EMPTY -- the one form that can only REMOVE inherited
#: config, never add behaviour. `-o addopts=<anything>`, `-o junit_suite_name=x`
#: and bare `-o` all stay refused, pinned by tests.
_PYTEST_CLEAR_ADDOPTS = r"(?: -o addopts=(?= |$))"

#: Either kind of flag may appear on either side of the target.
_ALLOWED_FLAG = f"(?:{_PYTEST_READ_ONLY_FLAG}|{_PYTEST_CLEAR_ADDOPTS})"
_SANDBOX_TEST_FILE = r"(?: \"?(?:training_ground|lab)[/\\][A-Za-z0-9_\-]+\.py\"?)"
ALLOWED_CMD_RE = re.compile(
    r"^(?:python -m )?pytest"
    + _ALLOWED_FLAG + "*"
    + _SANDBOX_TEST_FILE + "?"
    + _ALLOWED_FLAG + "*$"
)


#: Example commands the gate admits, and the one-line policy the harness states
#: to the agent before a mission starts.
#:
#: Organ 44 cohorts kept losing a mission to output formatting: -v, --no-header,
#: -s, --tb=, -o addopts=, then -o console_output_style=classic. Each widening
#: was individually correct and each time a different model reached for a
#: different spelling, because the agent was never told what would be approved.
#: The cohort was partly measuring its ability to GUESS AN UNPUBLISHED RULE,
#: which is not what organ 44 is for.
#:
#: A real operator says what they will approve. This is that sentence.
#:
#: NOT a widening: the gate is unchanged and still refuses everything it
#: refused before. Every example below is asserted against ALLOWED_CMD_RE
#: itself by tests/test_probe_allowlist.py, so a narrowed gate breaks the
#: policy text rather than silently misleading the agent -- the drift that
#: caused this in the first place.
APPROVAL_POLICY_EXAMPLES: tuple[str, ...] = (
    "pytest training_ground/test_x.py",
    "python -m pytest training_ground/test_x.py -q",
    "pytest -v training_ground/test_x.py",
    'python -m pytest -o addopts= "training_ground/test_x.py" -q',
)


def approval_policy_text() -> str:
    """What the approving operator will and will not sign off, stated plainly."""
    examples = "\n".join(f"    {c}" for c in APPROVAL_POLICY_EXAMPLES)
    return (
        "OPERATOR APPROVAL POLICY (read before requesting approval)\n"
        "\n"
        "I approve exactly one kind of command: pytest, run on a single test "
        "file inside training_ground/ or lab/. For example:\n"
        f"{examples}\n"
        "\n"
        "Output-only flags are fine (-q, -qq, -v, -vv, -s, --no-header, "
        "--collect-only, --tb=<style>, and -o addopts= with an empty value).\n"
        "\n"
        "I will REFUSE anything else, and a refused command ends the task. "
        "That includes -k and -x (they change which tests run), -p, --pdb, "
        "--noconftest, --rootdir, -c, any other -o option, more than one file, "
        "a path outside training_ground/ or lab/, and any program that is not "
        "pytest.\n"
        "\n"
        "If you only want different output formatting, prefer plain "
        "`pytest <file>` -- it is always approved."
    )
