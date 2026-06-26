"""Daily-use probe: ask AI-OS to create a tiny file and verify the full loop.

This exercises the real backend (/api/generate), the approval gate, and the
sandbox write path in training_ground/. It does NOT drive the browser; it
validates the agentic loop that the frontend relies on.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

# Allow importing ``aios.*`` when this script is executed directly from
# ``tools/`` or from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aios.probe_common import BASE
SESSION_ID = "daily-use-probe-2026-06-24"
TARGET = Path("training_ground/daily_use_probe_result.py")


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code} for {path}: {body}") from exc


def generate(prompt: str, tokens: list[str] | None = None) -> dict:
    """Call /api/generate and parse the SSE stream."""
    payload = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "modelId": "auto",
        "sessionId": SESSION_ID,
        "approvalTokens": tokens or [],
    }
    req = urllib.request.Request(
        f"{BASE}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    events: list[dict] = []
    approval_token: str | None = None
    text = ""
    with urllib.request.urlopen(req, timeout=300) as resp:
        for line in resp:
            line = line.decode("utf-8").rstrip("\n")
            if line.startswith("event:"):
                events.append({"event": line.split(":", 1)[1].strip(), "data": {}})
            elif line.startswith("data:") and events:
                data_str = line.split(":", 1)[1].strip()
                try:
                    events[-1]["data"] = json.loads(data_str)
                except json.JSONDecodeError:
                    events[-1]["data"] = {"text": data_str}
    for ev in events:
        if ev["event"] == "human_required":
            approval_token = (
                ev["data"].get("approvalToken")
                or ev["data"].get("token")
                or (ev["data"].get("input") or {}).get("approvalToken")
            )
        if ev["event"] == "text_chunk":
            text += str(ev["data"].get("text", ""))
    # Print all step events for debugging.
    for ev in events:
        if ev["event"] == "step":
            print(f"[probe step] {ev['data'].get('type')} {ev['data'].get('tool')}: {str(ev['data'].get('output', ''))[:120]}")
    return {"events": events, "approvalToken": approval_token, "text": text}


def approve(token: str) -> dict:
    return post(
        "/api/v1/approval/req",
        {"approvalToken": token, "sessionId": SESSION_ID, "approve": True},
    )


def main() -> int:
    # Clean any prior probe artifact.
    TARGET.unlink(missing_ok=True)

    health = urllib.request.urlopen(f"{BASE}/health", timeout=10).status
    assert health == 200, f"backend health check failed: {health}"
    print("[probe] backend health OK")

    prompt = (
        "Use the create_file tool to create training_ground/daily_use_probe_result.py "
        "containing a Python function greet(name) that returns 'Hello, {name}!. "
        "Do not ask for permission; just call the tool."
    )
    print("[probe] sending directive...")
    result = generate(prompt)

    if not result["approvalToken"]:
        print("[probe] WARNING: no approval token returned; model response:")
        print(result["text"][:500])
        # Some models/flows may skip approval for create actions; still check file.
        time.sleep(2)
        if TARGET.exists():
            print("[probe] SUCCESS: file was created without approval token")
            print(TARGET.read_text())
            return 0
        print("[probe] FAILURE: no approval token and no file created")
        return 1

    print(f"[probe] approval token received: {result['approvalToken'][:12]}...")
    # create_file/edit_file approvals are replayed through /api/generate with the
    # server-issued token; /api/v1/approval/req only handles command approvals.
    print("[probe] replaying turn with approved token...")
    result2 = generate(prompt, [result["approvalToken"]])
    print(f"[probe] replay complete; paused={result2.get('paused')}")

    # Wait briefly for the agent to execute the approved action.
    for _ in range(30):
        if TARGET.exists():
            break
        time.sleep(0.5)

    if not TARGET.exists():
        print("[probe] FAILURE: file did not appear after approval")
        return 1

    content = TARGET.read_text()
    print("[probe] SUCCESS: file created")
    print(content)

    if "greet" not in content.lower():
        print("[probe] WARNING: file does not contain expected 'greet' function")
    return 0


if __name__ == "__main__":
    sys.exit(main())
