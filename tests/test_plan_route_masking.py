"""The operator's plans see GAGOS's identifiers (2026-11-13).

His decision of 2026-11-11: for GAGOS's tracked code sent to his Claude and
Codex plans, hide only keys, credentials and local paths, and show
identifiers; Bedrock and every other route keep the full filter. Before it,
the full filter's high-entropy layer hid any 21-character name standing where
it did not recognise code: writers were refused tasks whose names they could
not see (PERF-04), and a reviewer was shown the reset function a test imports
hidden on one line and plain on the next (gd-f98e938baf).
"""

from __future__ import annotations

import json
import subprocess

import pytest

from aios.core import plan_cli
from aios.core.privacy_filter import PrivacyFilter
from aios.maintenance.daily_work import mask_lines, unmask
from tools import gagos_daily as tool

IMPORTS = (
    "import {\n"
    "  __resetSpineFlashBridgeForTests,\n"
    "  subscribeToSpineFlashes,\n"
    "} from './spineFlashBridge';\n"
    "beforeEach(() => __resetSpineFlashBridgeForTests());\n"
)
KEY = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
PATH = r"C:\Users\someone\secrets\notes.txt"


def _sent(text: str, **kw) -> str:
    safe, _ = PrivacyFilter(**kw).filter([{"role": "user", "content": text}])
    return safe[0]["content"]


def test_the_plans_route_shows_identifiers_the_full_filter_hides() -> None:
    assert _sent(IMPORTS, identifiers_shown=True) == IMPORTS
    assert "__resetSpineFlashBridgeForTests,\n" not in _sent(IMPORTS)


@pytest.mark.parametrize("value", [KEY, PATH, "AKIA" + "ABCDEFGHIJKLMNOP"])
def test_keys_credentials_and_local_paths_stay_hidden_on_the_plans_route(
    value,
) -> None:
    text = f"const where = '{value}';\n"
    assert value not in _sent(text, identifiers_shown=True)
    assert value not in tool.plan_egress_redact(text)


def test_the_gateways_secret_policy_still_scrubs_the_plans_route() -> None:
    from aios.runtime.secret_policy import SecretPolicy

    text = f"token = '{KEY}'\n"
    assert SecretPolicy().inspect_text(text).scrubbed != text
    assert KEY not in tool.plan_egress_redact(text)


def test_masking_for_the_plans_hides_only_what_their_route_would() -> None:
    code = IMPORTS + f"// notes in {PATH}\n"
    plan_masked, plan_map = mask_lines(code, tool.plan_mask_redact)
    full_masked, full_map = mask_lines(code, tool.mask_redact)
    assert "  __resetSpineFlashBridgeForTests,\n" in plan_masked
    assert "  __resetSpineFlashBridgeForTests,\n" not in full_masked
    assert PATH not in plan_masked and PATH not in full_masked
    assert set(plan_map.values()) < set(full_map.values()) | {PATH}
    assert unmask(plan_masked, plan_map, masked=plan_masked) == code


def test_the_workshops_plan_writers_send_with_identifiers_shown(
    monkeypatch,
) -> None:
    made = []
    monkeypatch.setattr(
        plan_cli, "PlanCliClient", lambda **kw: made.append(kw) or object()
    )
    tool.plan_writer(tool.CLAUDE_WRITERS[0])
    assert made[0]["identifiers_shown"] is True


def test_the_counter_keeps_the_full_filter() -> None:
    client = plan_cli.PlanCliClient(
        claude_models=("claude-sonnet-5-5",), claude="claude", codex="codex"
    )
    assert client._privacy_filter.identifiers_shown is False


def test_a_plan_client_with_identifiers_shown_sends_them(tmp_path) -> None:
    seen = []

    def run(argv, **kw):
        seen.append(kw.get("input", ""))
        return subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps({"result": "ok"}), stderr=""
        )

    client = plan_cli.PlanCliClient(
        claude_models=("claude-sonnet-5-5",),
        run=run,
        claude="claude",
        codex="codex",
        identifiers_shown=True,
    )
    client.complete(IMPORTS)
    assert "__resetSpineFlashBridgeForTests,\n" in seen[0]


# -- which build a writer is given ----------------------------------------------------


def _job(tag: str) -> tuple:
    return (tag, "text", tag, {}, tag, "system", {}, None, None)


def test_a_plan_writer_takes_the_plans_build_and_bedrock_the_full_one() -> None:
    job = (*_job("plan"), _job("full"))
    assert tool.job_for(job, tool.CLAUDE_WRITERS[0])[2] == "plan"
    assert tool.job_for(job, tool.CODEX_WRITERS[0])[2] == "plan"
    assert tool.job_for(job, tool.BEDROCK_WRITERS[0])[2] == "full"


def test_what_only_the_plans_may_see_is_refused_to_bedrock() -> None:
    job = (*_job("plan"), "the privacy filter would redact this file")
    assert tool.job_for(job, tool.BEDROCK_WRITERS[0]) == (
        "the privacy filter would redact this file"
    )
    assert tool.job_for(job, tool.CLAUDE_WRITERS[0])[2] == "plan"


def test_one_build_serves_every_writer() -> None:
    job = (*_job("full"), None)
    assert tool.job_for(job, tool.BEDROCK_WRITERS[0])[2] == "full"
    assert tool.job_for(job, tool.CLAUDE_WRITERS[0])[2] == "full"


@pytest.mark.parametrize(
    "plan,full,expected",
    [
        (("job", _job("p")), ("job", _job("f")), ("job", (*_job("p"), _job("f")))),
        (("job", _job("p")), ("refuse", "why"), ("job", (*_job("p"), "why"))),
        (("refuse", "p-why"), ("job", _job("f")), ("job", (*_job("f"), None))),
        (("refuse", "p-why"), ("refuse", "f-why"), ("refuse", "f-why")),
        (("wait", "held"), ("wait", "held"), ("wait", "held")),
    ],
)
def test_a_task_is_built_for_both_routes(plan, full, expected) -> None:
    assert tool.both_routes(plan, full) == expected
