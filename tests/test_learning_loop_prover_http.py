"""Exercise the prover against real mutation/auth guards without a model.

Only the downstream generation and skill payloads are fixtures. Enrollment,
login, reauthentication, session cookies and CSRF validation remain real.
"""

from __future__ import annotations

from argparse import Namespace
import json

import pytest
import requests
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from aios import config, probe_common, probe_session
from aios.api import deps
from aios.api.routes import auth
from aios.application.identity.service import IdentityService
from aios.interfaces.http import edge_security
from aios.policy.kernel import get_policy_kernel
from tools import learning_loop_prover as prover


class _RequestsBridge:
    """Adapt only the network transport; preserve HTTP responses and cookies."""

    def __init__(self, client: TestClient):
        self.client = client
        self.cookies = client.cookies

    def _request(self, method, url, **kwargs):
        kwargs.pop("stream", None)
        kwargs.pop("timeout", None)  # In-process transport has no socket timeout.
        result = self.client.request(method, url, **kwargs)
        response = requests.Response()
        response.status_code = result.status_code
        response.url = str(result.url)
        response.headers.update(result.headers)
        response._content = result.content
        response._content_consumed = True
        response.encoding = "utf-8"
        return response

    def post(self, url, **kwargs):
        return self._request("POST", url, **kwargs)

    def get(self, url, **kwargs):
        return self._request("GET", url, **kwargs)


@pytest.fixture
def guarded_api(monkeypatch, tmp_path):
    get_policy_kernel().clear_endpoint_hits()
    monkeypatch.delenv("AIOS_OPERATOR_CREDENTIAL", raising=False)
    monkeypatch.delenv("AIOS_API_TOKEN", raising=False)
    monkeypatch.setattr(config, "API_TOKEN", "")
    monkeypatch.setattr(probe_common, "API_TOKEN", "")
    monkeypatch.setattr(
        config, "CONSTITUTION_SNAPSHOT_DB_PATH", tmp_path / "constitution.db"
    )
    identity = IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )
    monkeypatch.setattr(edge_security, "get_session_manager", lambda: identity.sessions)
    api = FastAPI()
    api.state.identity = identity
    api.state.refuse_skills = False
    api.include_router(auth.router)
    api.dependency_overrides[deps.get_identity_service] = lambda: identity

    @api.middleware("http")
    async def mutation_guard(request, call_next):
        refusal = (
            edge_security.get_edge_trust_authority().check_mutation_origin_or_token(
                request
            )
        )
        return refusal if refusal is not None else await call_next(request)

    @api.post("/api/generate")
    def generate(principal=Depends(deps.require_privileged_operator)):
        return StreamingResponse(
            iter(["event: done\ndata: {}\n\n"]), media_type="text/event-stream"
        )

    @api.get("/api/v1/development/skills")
    def skills(principal=Depends(deps.require_privileged_operator)):
        if api.state.refuse_skills:
            raise HTTPException(status_code=403, detail="access refused")
        return {"skills": [{"name": "llp_reflex_abc", "status": "verified"}]}

    # Do not pass client=(loopback,...): conftest otherwise fabricates an
    # authenticated session before the driver can establish its own.
    client = TestClient(api)
    client.headers.clear()  # conftest also supplies Origin by default.
    bridge = _RequestsBridge(client)
    monkeypatch.setattr(probe_session.requests, "Session", lambda: bridge)
    monkeypatch.setattr(prover.requests, "post", bridge.post)
    monkeypatch.setattr(prover.requests, "get", bridge.get)
    monkeypatch.setattr(prover, "_PROBE_SESSION", None, raising=False)
    monkeypatch.setattr(prover, "PROMOTION_POLL_DELAY_S", 0)
    yield bridge
    client.close()
    get_policy_kernel().clear_endpoint_hits()


def test_prompt_establishes_and_reuses_a_real_operator_session(guarded_api):
    """Bare POST regresses to the exact nightly 403, before generation."""
    for name in ("first-turn", "second-turn"):
        try:
            result = prover.run_prompt("Report your status", name)
        except requests.HTTPError as exc:
            pytest.fail(f"prover could not enter guarded API: {exc.response.text}")
        assert result["outcome"] == "unverified"  # no fabricated verification


def test_skill_poll_uses_the_authenticated_session(guarded_api):
    assert prover.skill_promoted("llp_reflex_abc") is True


def test_skill_poll_recovers_from_a_revoked_session(guarded_api):
    prover.run_prompt("Report your status", "first-turn")
    old_cookie = guarded_api.cookies.get("session_id")
    identity = guarded_api.client.app.state.identity
    identity.revoke_session(old_cookie)
    assert identity.get_authenticated_principal(old_cookie) is None

    assert prover.skill_promoted("llp_reflex_abc") is True
    assert guarded_api.cookies.get("session_id") != old_cookie


def test_skill_poll_surfaces_refusal_instead_of_missing_skill(guarded_api):
    guarded_api.client.app.state.refuse_skills = True
    with pytest.raises(requests.HTTPError) as failure:
        prover.skill_promoted("llp_reflex_abc")
    assert failure.value.response.status_code == 403


@pytest.mark.parametrize("failure_after_checks", [False, True])
def test_interrupted_run_never_records_success(
    monkeypatch, tmp_path, failure_after_checks
):
    """An exception before/after a green check must leave a failed artifact."""
    monkeypatch.setattr(prover, "ROOT", tmp_path)
    monkeypatch.setattr(prover, "AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr(prover, "LOG_PATH", tmp_path / "audit" / "runs.jsonl")
    monkeypatch.setattr(prover, "preflight", lambda _: {"staleness": "fresh"})

    def interrupted(files, run_id, model, check):
        if failure_after_checks:
            check.hard("completed-before-disconnect", True, "observed")
        raise requests.ConnectionError("transport stopped")

    monkeypatch.setattr(prover, "phase_lesson", interrupted)
    args = Namespace(allow_stale=False, model="auto", lenient=True, keep_seeds=False)
    with pytest.raises(requests.ConnectionError):
        prover.cmd_run(args)
    rows = [json.loads(line) for line in prover.LOG_PATH.read_text().splitlines()]
    assert rows[-1]["kind"] == "prover-summary"
    assert rows[-1]["passed"] is False
    assert rows[-1]["completed"] is False
    assert list((tmp_path / "lab").glob("*.py")), "failed-run seeds must survive"


def test_completed_green_run_records_success_and_cleans_seeds(monkeypatch, tmp_path):
    monkeypatch.setattr(prover, "ROOT", tmp_path)
    monkeypatch.setattr(prover, "AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr(prover, "LOG_PATH", tmp_path / "audit" / "runs.jsonl")
    monkeypatch.setattr(prover, "preflight", lambda _: {"staleness": "fresh"})

    def green_phase(files, run_id, model, check):
        check.hard("fixture-check", True, "artifact control; no model exercised")

    for phase in ("phase_lesson", "phase_reflex", "phase_probe"):
        monkeypatch.setattr(prover, phase, green_phase)
    args = Namespace(allow_stale=False, model="auto", lenient=True, keep_seeds=False)
    with pytest.raises(SystemExit) as result:
        prover.cmd_run(args)
    assert result.value.code == 0
    rows = [json.loads(line) for line in prover.LOG_PATH.read_text().splitlines()]
    assert rows[-1]["passed"] is True
    assert rows[-1]["completed"] is True
    assert not list((tmp_path / "lab").glob("*.py"))


@pytest.mark.parametrize(
    ("checks", "completed", "expected"),
    [
        ([], None, "FAIL"),  # Existing artifacts from the nightly 0/0 defect.
        ([{"ok": True}], False, "FAIL"),
        ([{"ok": False, "downgraded": False}], None, "FAIL"),
        ([{"ok": True}], None, "PASS"),  # Valid older format stays readable.
    ],
)
def test_report_does_not_trust_an_inconsistent_pass_flag(
    monkeypatch, tmp_path, capsys, checks, completed, expected
):
    log_path = tmp_path / "runs.jsonl"
    record = {
        "kind": "prover-summary",
        "run_id": "historical-run",
        "passed": True,
        "checks": checks,
    }
    if completed is not None:
        record["completed"] = completed
    original = json.dumps(record) + "\n"
    log_path.write_text(original)
    monkeypatch.setattr(prover, "LOG_PATH", log_path)

    prover.cmd_report(Namespace())

    output = capsys.readouterr().out
    assert f"historical-run: {expected}" in output
    assert f"latest: {expected} @ historical-run" in output
    assert log_path.read_text() == original, "report must preserve historical evidence"
