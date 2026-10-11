"""The sovereignty drills judge honestly: a pass needs the thing to have happened.

The drills themselves run the real app and the real local model (minutes,
an Ollama daemon); what is pinned here is the instrument, without a model:

* a turn the local model did not answer is never a pass;
* failover that never tried the cloud is NOT_REACHED, never a pass;
* a privacy drill whose cloud transport was never called is NOT_REACHED;
* any canary at the transport is a FAIL; the system prompt being sent is
  recorded, not judged (the filter does not claim to withhold it);
* the network cut blocks everything but loopback; the transport records every
  request on both Converse paths and fails on demand.
"""

from __future__ import annotations

import socket

import pytest

from tools import sovereignty_drills as sd

OK = {"status": 200, "served_by": ["ollama"], "answer": "Paris.", "cloud_attempts": 1}


@pytest.mark.parametrize("drill", ["offline", "failover"])
def test_the_local_model_answering_is_a_pass(drill) -> None:
    assert sd.judge(drill, OK)[0] == sd.PASS


@pytest.mark.parametrize("drill", ["offline", "failover"])
def test_no_answer_or_a_cloud_answer_is_a_fail(drill) -> None:
    assert sd.judge(drill, {**OK, "answer": "  "})[0] == sd.FAIL
    assert sd.judge(drill, {**OK, "served_by": ["ollama", "bedrock"]})[0] == sd.FAIL
    assert sd.judge(drill, {**OK, "served_by": []})[0] == sd.FAIL


def test_failover_that_never_tried_the_cloud_measured_nothing() -> None:
    assert sd.judge("failover", {**OK, "cloud_attempts": 0})[0] == sd.NOT_REACHED
    # Offline is about serving locally with the network cut, whoever was tried.
    assert sd.judge("offline", {**OK, "cloud_attempts": 0})[0] == sd.PASS


def test_privacy_needs_the_cloud_to_have_been_asked() -> None:
    clean = {**OK, "canaries_sent": {"access_key": False, "local_path": False}}
    assert sd.judge("privacy", clean)[0] == sd.PASS
    assert sd.judge("privacy", {**clean, "cloud_attempts": 0})[0] == sd.NOT_REACHED


@pytest.mark.parametrize("canary", ["access_key", "local_path"])
def test_any_canary_at_the_transport_fails(canary) -> None:
    sent = {"access_key": False, "local_path": False, canary: True}
    verdict, why = sd.judge("privacy", {**OK, "canaries_sent": sent})
    assert verdict == sd.FAIL and canary in why


def test_the_system_prompt_is_recorded_not_judged() -> None:
    obs = {
        **OK,
        "canaries_sent": {"access_key": False, "local_path": False},
        "system_prompt_sent": True,
    }
    verdict, why = sd.judge("privacy", obs)
    assert verdict == sd.PASS and "system prompt is sent" in why


@pytest.mark.parametrize("drill", sd.DRILLS)
def test_errors_and_refusals_are_never_verdicts(drill) -> None:
    assert sd.judge(drill, {"error": "the local model did not answer"})[0] == sd.ERROR
    assert sd.judge(drill, {**OK, "status": 401})[0] == sd.ERROR


def test_the_transport_records_and_fails_on_both_paths() -> None:
    from botocore.exceptions import ClientError

    ok = sd._Transport(fail=False)
    assert ok.converse(modelId="m")["output"]["message"]["content"][0]["text"]
    assert ok.converse_stream(modelId="m")["stream"]
    assert len(ok.requests) == 2
    bad = sd._Transport(fail=True)
    for call in (bad.converse, bad.converse_stream):
        with pytest.raises(ClientError, match="Throttling"):
            call(modelId="m")
    assert len(bad.requests) == 2, "a failed call is still a recorded attempt"


def test_the_network_cut_allows_only_loopback() -> None:
    cut = sd._SocketCut()
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        cut.install()
        with socket.socket() as client:
            client.connect(("127.0.0.1", port))  # loopback still works
        with socket.socket() as client, pytest.raises(ConnectionRefusedError):
            client.connect(("93.184.216.34", 443))
        with pytest.raises(socket.gaierror):
            socket.getaddrinfo("bedrock-runtime.ap-south-1.amazonaws.com", 443)
        assert "93.184.216.34" in cut.blocked
        assert "bedrock-runtime.ap-south-1.amazonaws.com" in cut.blocked
    finally:
        socket.socket.connect = cut._connect  # type: ignore[method-assign]
        socket.socket.connect_ex = cut._connect_ex  # type: ignore[method-assign]
        socket.getaddrinfo = cut._getaddrinfo  # type: ignore[assignment]
        server.close()


def test_drills_never_hold_a_real_cloud_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "a-real-looking-key")
    monkeypatch.setenv("AIOS_OPENAI_API_KEY", "another")
    env = sd._env(tmp_path, "offline")
    assert env["AWS_BEARER_TOKEN_BEDROCK"] == "drill-placeholder-not-a-key"
    assert "AIOS_OPENAI_API_KEY" not in env
    assert env["AIOS_RUNTIME_PROFILE"] == sd.CLOUD_PRIMARY_PROFILE, (
        "cloud must be primary to fail over"
    )
    assert "AIOS_RUNTIME_PROFILE" not in sd._env(tmp_path, "privacy")


def test_the_cloud_primary_profile_really_prefers_cloud_for_the_drill_task() -> None:
    """The drill is only meaningful if its profile lets the task leave the
    machine and does not prefer local; guard against profiles.json drifting."""
    from aios.core.model_selector import infer_task
    from aios.runtime import profiles

    profile = profiles.get_profile(sd.CLOUD_PRIMARY_PROFILE)
    assert profile is not None
    task = infer_task(sd.QUESTION)
    assert task in profile.router_cloud_tasks, (task, profile.router_cloud_tasks)
    assert profile.router_prefer_local is False
