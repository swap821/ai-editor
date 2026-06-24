#!/usr/bin/env python3
"""End-to-end demo: cloud-burst ant-colony emits a cloud_route SSE frame.

The local LLM is replaced by scripted fakes via dependency override; the cloud
provider is replaced by patching BedrockClient in aios.api.main. No real cloud
credentials are used.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

# Make the project root importable when running from tests/e2e/.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("AIOS_INTERPRET_ALIGNMENT", "false")
os.environ.setdefault("AIOS_INDEX_CHAT", "false")
os.environ.setdefault("AIOS_REFLECT_ON_FAILURE", "false")
# Enable cloud-burst and a dummy Bedrock region BEFORE importing config/app so
# run_swarm's default cloud_burst value is True and the generate() branch builds
# a cloud client. The real BedrockClient class is patched below.
os.environ.setdefault("AIOS_SWARM_CLOUD_BURST", "true")
os.environ.setdefault("AIOS_BEDROCK_REGION", "us-east-1")
os.environ.setdefault("AIOS_BEDROCK_MODEL", "bedrock.fake-model")

from fastapi.testclient import TestClient

import aios.api.main as main_mod
import aios.config as config_mod
from aios.api.main import app, get_ollama_client, get_bedrock_client

# Cap the swarm so the scripted fake has exactly the responses it needs.
config_mod.SWARM_MAX_WORKERS = 2
config_mod.SWARM_WORKER_CONCURRENCY = 1
config_mod.SWARM_REDUNDANCY = 1


def _tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
    }


class FakeChat:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, Any]]] = []

    def chat(self, messages: list[dict[str, Any]], *, tools: Any = None, model: Any = None) -> dict[str, Any]:
        self.calls.append(messages)
        return self._responses.pop(0)


class CloudFake:
    """Patch target for aios.api.main.BedrockClient inside generate()."""

    _responses: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    def chat(self, messages: list[dict[str, Any]], *, tools: Any = None, model: Any = None) -> dict[str, Any]:
        self.calls.append(messages)
        return self._responses.pop(0)


main_mod.BedrockClient = CloudFake  # type: ignore[misc]


def parse_sse(response) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    current: dict[str, object] = {}
    for raw in response.iter_lines():
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if line.startswith("event: "):
            current["event"] = line[len("event: "):]
        elif line.startswith("data: "):
            current.setdefault("data", []).append(line[len("data: "):])
        elif line == "":
            if "event" in current:
                payload = json.loads("".join(current.get("data", [])))  # type: ignore[arg-type]
                events.append({"event": current["event"], "data": payload})
            current = {}
    return events


def main() -> int:
    session_id = f"cloud-{uuid.uuid4().hex[:8]}"

    CloudFake._responses = [
        # cloud worker-1: echo via execute_terminal (GREEN), then report.
        _tool_call("execute_terminal", {"command": 'echo "cloud worker done"'}),
        {"role": "assistant", "content": "Cloud worker reported."},
    ]

    local_fake = FakeChat([
        # decomposer
        {"role": "assistant", "content": "1. Echo cloud status\n2. Echo local status"},
        # cloud broker
        {"role": "assistant", "content": "1. CLOUD\n2. LOCAL"},
        # local worker-2: echo (GREEN), then report.
        _tool_call("execute_terminal", {"command": 'echo "local worker done"'}),
        {"role": "assistant", "content": "Local worker reported."},
        # synthesizer
        {"role": "assistant", "content": "All workers reported successfully."},
    ])

    app.dependency_overrides[get_ollama_client] = lambda: local_fake
    app.dependency_overrides[get_bedrock_client] = lambda: CloudFake()

    body = {
        "sessionId": session_id,
        "modelId": "ollama.qwen2.5-coder:3b",
        "messages": [{"role": "user", "content": "report cloud and local status"}],
        "approvalTokens": [],
        "swarm": True,
    }

    with TestClient(app) as client:
        with client.stream("POST", "/api/generate", json=body) as resp:
            resp.raise_for_status()
            events = parse_sse(resp)

    cloud_routes = [e for e in events if e.get("event") == "cloud_route"]
    if not cloud_routes:
        print("[cloud] FAIL: no cloud_route frame emitted")
        for ev in events:
            if ev.get("event") in ("caste_start", "cloud_route", "step", "done"):
                print("  ", ev.get("event"), json.dumps(ev.get("data"), default=str)[:240])
        return 1

    cr = cloud_routes[0]["data"]
    print(f"[cloud] PASS: cloud_route frame = {cr}")
    assert cr.get("role") == "swarm"
    assert cr.get("provider") == "bedrock"
    assert isinstance(cr.get("subtask_index"), int)

    done_events = [e for e in events if e.get("event") == "done"]
    print(f"[cloud] swarm completed; {len(done_events)} done frame(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
