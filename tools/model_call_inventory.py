"""Which model calls pass the one gateway? Measured by driving the real app.

    python tools/model_call_inventory.py                 # every surface
    python tools/model_call_inventory.py --only generate_local
    python tools/model_call_inventory.py --out report.json

The real app runs in a child process on a throwaway data directory (the
red-team reel's isolated Harness), with its REAL provider adapters:

* Ollama is the real ``OllamaClient`` talking HTTP to a fake Ollama server this
  tool runs. The server answers instantly and identically every time; there is
  no model.
* Bedrock is the real ``BedrockClient`` over a recording transport.

Each surface (a route, or a background path a route starts) is driven once.
The model-call ledger (``aios/core/model_calls.py``) then says, for every call,
which gateway entrance it came through -- or that it came through none -- and
which code asked for it.

Two integrity checks make the ledger itself trustworthy, not just read:

* every request the fake server and the transport RECEIVED has a ledger record
  (a model call the ledger missed would otherwise read as no call at all);
* a surface that made no model call is reported as NOT REACHED, never as clean.

Verdict per call: ``gated`` (an entrance) or ``UNGATED`` (none). The tool
measures; it fixes nothing.
"""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FAKE_MODEL = "qwen2.5:0.5b"
FAKE_ANSWER = "Paris."
CLOUD_MODEL = "deepseek.v3.2"
#: A JSON answer for callers that ask for JSON mode: valid, and empty.
FAKE_JSON = "{}"
#: Prompts the fake recognises, and what it answers them with. The alignment
#: interpreter reads a non-JSON answer as low confidence, and the forge then
#: stops to ask a question before the agent's model is ever called -- so the
#: fake answers it as a clear request would be read.
SCRIPTED = (
    (
        "Interpret the latest USER request",
        json.dumps(
            {
                "goal": "Answer a factual question",
                "intent": "discuss",
                "desired_outcome": "A one-line answer",
                "confidence": 0.95,
                "assumptions": [],
                "unknowns": [],
            }
        ),
    ),
)


# --------------------------------------------------------------------------- #
# The fake model server (Ollama's HTTP API) and the fake Bedrock transport
# --------------------------------------------------------------------------- #


class FakeOllama:
    """An Ollama-shaped HTTP server with no model. Counts model requests."""

    MODEL_PATHS = ("/api/chat", "/api/generate")

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # silence
                return

            def _send(self, body: bytes, ctype: str = "application/json") -> None:
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802 - http.server API
                if self.path.startswith("/api/tags"):
                    model = {
                        "name": FAKE_MODEL,
                        "model": FAKE_MODEL,
                        "size": 397_000_000,
                        "details": {
                            "family": "qwen2",
                            "parameter_size": "494M",
                            "quantization_level": "Q4_K_M",
                        },
                    }
                    self._send(json.dumps({"models": [model]}).encode())
                elif self.path.startswith("/api/ps"):
                    self._send(json.dumps({"models": []}).encode())
                else:
                    self._send(b"{}")

            def do_POST(self) -> None:  # noqa: N802 - http.server API
                length = int(self.headers.get("Content-Length") or 0)
                try:
                    payload = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    payload = {}
                path = self.path.split("?")[0]
                if path not in outer.MODEL_PATHS:
                    self._send(b"{}")
                    return
                with outer._lock:
                    outer.requests.append(
                        {
                            "path": path,
                            "model": payload.get("model"),
                            "stream": payload.get("stream"),
                        }
                    )
                text = FAKE_JSON if payload.get("format") == "json" else FAKE_ANSWER
                asked = json.dumps(
                    payload.get("prompt") or payload.get("messages") or ""
                )
                for marker, scripted in SCRIPTED:
                    if marker in asked:
                        text = scripted
                if path == "/api/chat":
                    message = {"role": "assistant", "content": text}
                    if payload.get("stream"):
                        lines = [
                            {"message": message, "done": False},
                            {
                                "message": {"role": "assistant", "content": ""},
                                "done": True,
                            },
                        ]
                        body = "\n".join(json.dumps(x) for x in lines).encode()
                        self._send(body, "application/x-ndjson")
                    else:
                        self._send(
                            json.dumps({"message": message, "done": True}).encode()
                        )
                else:
                    if payload.get("stream"):
                        lines = [
                            {"response": text, "done": False},
                            {"response": "", "done": True},
                        ]
                        body = "\n".join(json.dumps(x) for x in lines).encode()
                        self._send(body, "application/x-ndjson")
                    else:
                        self._send(
                            json.dumps({"response": text, "done": True}).encode()
                        )

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()


class FakeBedrock:
    """A Bedrock runtime transport with no model. Counts requests."""

    def __init__(self) -> None:
        self.requests: list[str] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append("converse")
        return {
            "output": {
                "message": {"role": "assistant", "content": [{"text": FAKE_ANSWER}]}
            },
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
        }

    def converse_stream(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append("converse_stream")
        return {
            "stream": [
                {"messageStart": {"role": "assistant"}},
                {"contentBlockDelta": {"delta": {"text": FAKE_ANSWER}}},
                {"messageStop": {"stopReason": "end_turn"}},
            ]
        }


class _NoDiscovery:
    def list_foundation_models(self, **_: Any) -> dict[str, Any]:
        return {"modelSummaries": []}

    def list_inference_profiles(self, **_: Any) -> dict[str, Any]:
        return {"inferenceProfileSummaries": []}


# --------------------------------------------------------------------------- #
# Surfaces: each drives one production path through the real app
# --------------------------------------------------------------------------- #


def _sse(response: Any) -> dict[str, Any]:
    """Status, the event names in order, and any error frame's text."""
    events: list[str] = []
    errors: list[str] = []
    event = ""
    for line in response.text.splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
            events.append(event)
        elif line.startswith("data:") and event == "error":
            errors.append(line.split(":", 1)[1].strip()[:300])
    return {
        "status": response.status_code,
        "events": events[:40],
        "stream_errors": errors,
        "body": "" if events else response.text[:300],
    }


def _generate(h: Any, model_id: str) -> dict[str, Any]:
    return _sse(
        h.client.post(
            "/api/generate",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": "What is the capital of France?"}],
                    }
                ],
                "sessionId": f"inventory-{model_id}",
                "modelId": model_id,
            },
        )
    )


def surface_generate_local(h: Any) -> dict[str, Any]:
    """The agentic forge, auto-routed (local-first): planner, CRAG, alignment."""
    return _generate(h, "auto")


def surface_generate_cloud(h: Any) -> dict[str, Any]:
    """The agentic forge with an explicit cloud model."""
    return _generate(h, CLOUD_MODEL)


def _chat(client: Any, transcript: str, session: str) -> dict[str, Any]:
    return _sse(
        client.post(
            "/api/v1/chat", json={"transcript": transcript, "sessionId": session}
        )
    )


def surface_chat(h: Any) -> dict[str, Any]:
    """Authenticated conversation (/api/v1/chat), conversation mode."""
    return _chat(h.client, "Tell me the capital of France.", "inv-chat")


def surface_chat_advisory(h: Any) -> dict[str, Any]:
    """Authenticated conversation whose directive reads as ADVISORY ("what is")."""
    return _chat(h.client, "What is the capital of France?", "inv-chat-advisory")


#: The bearer token the inventory's child accepts (a throwaway, like its root).
API_TOKEN = "model-call-inventory-token"


def surface_chat_bearer(h: Any) -> dict[str, Any]:
    """A client with the API token and no session: no authenticated principal,
    so conversation takes the local-only compatibility entrance."""
    from fastapi.testclient import TestClient

    with TestClient(h.app, client=("127.0.0.1", 12398)) as anon:
        anon.headers["Authorization"] = f"Bearer {API_TOKEN}"
        anon.headers["Host"] = "localhost:8000"
        return _chat(anon, "Tell me the capital of France.", "inv-bearer")


def surface_reflect(h: Any) -> dict[str, Any]:
    """Failure reflection (/api/v1/reflect)."""
    r = h.client.post(
        "/api/v1/reflect",
        json={
            "command": "pytest -q",
            "error_output": "E   assert 1 == 2",
            "task_id": "inv",
        },
    )
    return {"status": r.status_code}


def surface_plan(h: Any) -> dict[str, Any]:
    """Goal decomposition (/api/v1/plan)."""
    r = h.client.post("/api/v1/plan", json={"goal": "Add a docstring to a function"})
    return {"status": r.status_code}


def surface_generate_recall(h: Any) -> dict[str, Any]:
    """A forge turn with something to recall: the earlier turns are indexed into
    memory, so recall has hits and CRAG's judge -- a model call -- runs."""
    first = _generate(h, "auto")
    second = _generate(h, "auto")
    return {**second, "first_status": first.get("status")}


def _approved_post(client: Any, url: str, body: Any = None) -> Any:
    """POST, and if the route asks for a human's exact capability (428), grant
    it -- the inventory is the operator of its own throwaway root, as the
    red-team harness is -- by re-sending with the token it was handed."""
    kwargs = {"json": body} if body is not None else {}
    first = client.post(url, **kwargs)
    if first.status_code != 428:
        return first
    detail = first.json().get("detail") or {}
    token = detail.get("approvalToken") if isinstance(detail, dict) else None
    if not token:
        return first
    return client.post(url, headers={"X-AIOS-Capability": token}, **kwargs)


def surface_hiring(h: Any) -> dict[str, Any]:
    """One bounded advisory call through the hiring service."""
    r = _approved_post(
        h.client,
        "/api/v1/hiring/call",
        {
            "request_id": "inventory-hiring-1",
            "mission_id": "inventory",
            "purpose": "inventory",
            "prompt": "Say ok.",
            "data_classification": "PUBLIC",
            "allowed_providers": ["ollama"],
            "local_only": True,
        },
    )
    return {"status": r.status_code, "body": r.text[:300]}


def surface_clerk(h: Any) -> dict[str, Any]:
    """The local clerk: discover, approve (on the throwaway root), health-check,
    qualify -- every probe a model call."""
    base = f"/api/v1/local-workforce/{FAKE_MODEL}"
    statuses = {
        "refresh": _approved_post(h.client, "/api/v1/local-workforce/refresh"),
        "approve": _approved_post(h.client, f"{base}/approve", {"approved": True}),
        "health": _approved_post(h.client, f"{base}/health-check"),
    }
    qualify = _approved_post(h.client, f"{base}/qualify")
    return {
        "status": qualify.status_code,
        "steps": {name: r.status_code for name, r in statuses.items()},
        "body": qualify.text[:300],
    }


def surface_council(h: Any) -> dict[str, Any]:
    """Council origination: the Queen's deliberation runs as a background task."""
    from aios import config

    workspace = Path(config.COUNCIL_WORKSPACE_ROOT)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "notes.md").write_bytes(b"# notes" + bytes([10]))
    r = _approved_post(
        h.client,
        "/api/v1/council/missions",
        {"goal": "Add a one-line summary to notes.md", "allowedFiles": ["notes.md"]},
    )
    mission = (r.json() or {}).get("missionId") if r.status_code == 200 else None
    if mission:
        report = h.client.get(f"/api/v1/council/missions/{mission}")
        return {"status": r.status_code, "body": report.text[:4000]}
    return {"status": r.status_code, "body": r.text[:300]}


SURFACES: dict[str, Callable[[Any], dict[str, Any]]] = {
    "generate_local": surface_generate_local,
    "generate_cloud": surface_generate_cloud,
    "chat": surface_chat,
    "chat_advisory": surface_chat_advisory,
    "chat_bearer": surface_chat_bearer,
    "reflect": surface_reflect,
    "plan": surface_plan,
    "generate_recall": surface_generate_recall,
    "hiring": surface_hiring,
    "clerk": surface_clerk,
    "council": surface_council,
}


# --------------------------------------------------------------------------- #
# The child: the real app, real adapters, fake model endpoints
# --------------------------------------------------------------------------- #


def run_child(names: list[str], root: Path, out: Path, ollama_url: str) -> int:
    from tools import learning_redteam_runner as lrt

    fake_bedrock = FakeBedrock()
    report: dict[str, Any] = {"surfaces": {}}
    h = None
    try:
        from aios.api.deps import get_llm_client, get_ollama_client
        from aios.api.main import get_alignment_interpreter, get_bedrock_client
        from aios.core import model_calls
        from aios.core.bedrock import BedrockClient

        h = lrt.Harness(root)
        # The harness seats fakes for every model client; the inventory needs
        # the REAL adapters, so it takes those overrides back out.
        for dependency in (
            get_ollama_client,
            get_llm_client,
            get_alignment_interpreter,
        ):
            h.app.dependency_overrides.pop(dependency, None)
        bedrock = BedrockClient(
            model=CLOUD_MODEL,
            region="ap-south-1",
            client=fake_bedrock,
            ctrl_client=_NoDiscovery(),
        )
        h.app.dependency_overrides[get_bedrock_client] = lambda: bedrock
        # With an API token set, every request must carry it; the session
        # client keeps its session, so its turns stay authenticated.
        h.client.headers["Authorization"] = f"Bearer {API_TOKEN}"

        data_dir = root / "data"
        for name in names:
            before = len(_ledger(data_dir))
            try:
                result = SURFACES[name](h)
            except Exception as exc:  # noqa: BLE001 - reported, never a verdict
                result = {"error": f"{type(exc).__name__}: {exc}"[:300]}
            calls = _ledger(data_dir)[before:]
            result["calls"] = calls
            report["surfaces"][name] = result
        report["ledger_total"] = len(_ledger(data_dir))
        report["process_counts"] = sum(model_calls.counts().values())
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"{type(exc).__name__}: {exc}"[:400]
    finally:
        if h is not None:
            h.close()
    report["bedrock_requests"] = len(fake_bedrock.requests)
    out.write_text(json.dumps(report, default=str), encoding="utf-8")
    return 0


def _ledger(data_dir: Path) -> list[dict[str, Any]]:
    directory = data_dir / "model_calls"
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.jsonl")) if directory.is_dir() else []:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                records.append(
                    {
                        k: record.get(k)
                        for k in ("provider", "method", "entrance", "site", "stack")
                    }
                )
    return records


# --------------------------------------------------------------------------- #
# The parent
# --------------------------------------------------------------------------- #


def _env(root: Path, ollama_url: str) -> dict[str, str]:
    from tools import learning_redteam_runner as lrt

    env = lrt.child_environment(root)
    for name in list(env):
        if name.startswith(
            ("AWS_", "AIOS_OPENAI", "AIOS_ANTHROPIC", "GEMINI", "GOOGLE_API")
        ):
            env.pop(name)
    env.update(
        {
            "OLLAMA_HOST": ollama_url,
            "AIOS_LLM_MODEL": FAKE_MODEL,
            # Production defaults the reel turns off, back on: CRAG's judge is a
            # model call, and it must be counted.
            "AIOS_CRAG": "1",
            "AWS_BEARER_TOKEN_BEDROCK": "inventory-placeholder-not-a-key",
            "AIOS_BEDROCK_REGION": "ap-south-1",
            "AIOS_BEDROCK_MODEL": CLOUD_MODEL,
            "AIOS_API_TOKEN": API_TOKEN,
            "AIOS_COUNCIL_WORKSPACE_ROOT": str(root / "council_workspace"),
            # The council refuses to run without a verification key. This one
            # is random, made for this run, and dies with its throwaway root.
            "AIOS_VERIFICATION_AUTHORITY_KEY": secrets.token_hex(32),
        }
    )
    env.pop(lrt.BEHAVIOURAL_MODEL_ENV, None)
    return env


#: Method names a model client answers to. A static call of one of these is a
#: CANDIDATE model call: some are calls on other objects, which is why the
#: static list only measures coverage and never decides a verdict.
MODEL_METHODS = frozenset(
    {"chat", "complete", "stream_chat", "stream_chat_with_tools", "stream_complete"}
)


def static_call_sites(repo: Path = REPO_ROOT) -> list[str]:
    """``path:function`` of every candidate model call in ``aios/``.

    The function is the innermost def or lambda around the call -- the same
    name the ledger records as a call's site -- so the two lists compare.
    Calls inside the adapters and the gateway are plumbing, as in the ledger.
    """
    import ast

    from aios.core.model_calls import _PLUMBING

    sites: set[str] = set()
    for path in sorted((repo / "aios").rglob("*.py")):
        rel = path.relative_to(repo).as_posix()
        if rel in _PLUMBING:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))

        def visit(node: ast.AST, scope: str) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    visit(child, child.name)
                elif isinstance(child, ast.Lambda):
                    visit(child, "<lambda>")
                else:
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Attribute)
                        and child.func.attr in MODEL_METHODS
                    ):
                        sites.add(f"{rel}:{scope}")
                    visit(child, scope)

        visit(tree, "<module>")
    return sorted(sites)


def coverage(result: dict[str, Any], static: list[str]) -> dict[str, Any]:
    """Which static candidate sites the drive actually observed: a site counts
    when it is anywhere on a recorded call's stack, not only innermost (an
    outer caller that reaches the model through an inner one did run)."""
    observed = set(result.get("observed_frames") or ())
    return {
        "static_candidates": len(static),
        "observed": sorted(set(static) & observed),
        "not_observed": sorted(set(static) - observed),
        "observed_outside_static": sorted(observed - set(static)),
    }


def judge(report: dict[str, Any], ollama_requests: int) -> dict[str, Any]:
    """Pure: the inventory's verdicts, from the child's report."""
    surfaces: dict[str, Any] = {}
    ungated: dict[str, int] = {}
    gated: dict[str, int] = {}
    recorded = {"ollama": 0, "bedrock": 0}
    frames: set[str] = set()
    for name, result in (report.get("surfaces") or {}).items():
        calls = result.get("calls") or []
        for call in calls:
            frames.update(call.get("stack") or [call.get("site")])
            key = f"{call.get('site')} [{call.get('provider')}.{call.get('method')}]"
            bucket = gated if call.get("entrance") else ungated
            bucket[key] = bucket.get(key, 0) + 1
            if call.get("provider") in recorded:
                recorded[call["provider"]] += 1
        if result.get("error"):
            verdict = "error"
        elif not calls:
            verdict = "not_reached"
        elif all(call.get("entrance") for call in calls):
            verdict = "gated"
        else:
            verdict = "UNGATED"
        surfaces[name] = {
            "verdict": verdict,
            "status": result.get("status"),
            "calls": len(calls),
            "error": result.get("error"),
            "events": result.get("events"),
            "stream_errors": result.get("stream_errors"),
            "body": result.get("body"),
        }
    integrity = {
        "ollama_requests_received": ollama_requests,
        "ollama_calls_recorded": recorded["ollama"],
        "bedrock_requests_received": report.get("bedrock_requests", 0),
        "bedrock_calls_recorded": recorded["bedrock"],
    }
    integrity["ledger_complete"] = (
        integrity["ollama_requests_received"] == integrity["ollama_calls_recorded"]
        and integrity["bedrock_requests_received"]
        == integrity["bedrock_calls_recorded"]
    )
    return {
        "surfaces": surfaces,
        "ungated_sites": dict(sorted(ungated.items())),
        "gated_sites": dict(sorted(gated.items())),
        "observed_frames": sorted(f for f in frames if f),
        "integrity": integrity,
        "error": report.get("error"),
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")
    child = sub.add_parser("_child")
    child.add_argument("--root", type=Path, required=True)
    child.add_argument("--out", type=Path, required=True)
    child.add_argument("--ollama", required=True)
    child.add_argument("names", nargs="+")
    parser.add_argument("--only", choices=sorted(SURFACES), action="append")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.command == "_child":
        return run_child(args.names, args.root, args.out, args.ollama)

    names = args.only or list(SURFACES)
    server = FakeOllama()
    try:
        with tempfile.TemporaryDirectory(prefix="model-call-inventory-") as tmp:
            root = Path(tmp)
            out = root / "report.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "_child",
                    "--root",
                    str(root),
                    "--out",
                    str(out),
                    "--ollama",
                    server.url,
                    *names,
                ],
                cwd=str(REPO_ROOT),
                env=_env(root, server.url),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1800,
            )
            report = (
                json.loads(out.read_text(encoding="utf-8"))
                if out.is_file()
                else {
                    "error": f"child exited {proc.returncode}: {(proc.stderr or '')[-600:]}"
                }
            )
    finally:
        server.close()
    result = judge(report, len(server.requests))
    result["coverage"] = coverage(result, static_call_sites())
    for name, verdict in result["surfaces"].items():
        extra = f"  {verdict['error']}" if verdict.get("error") else ""
        print(f"{name:<16} {verdict['verdict']:<12} calls={verdict['calls']}{extra}")
    for site, count in result["ungated_sites"].items():
        print(f"  UNGATED x{count}: {site}")
    print(f"integrity: {result['integrity']}")
    cov = result["coverage"]
    print(
        f"coverage: {len(cov['observed'])} of {cov['static_candidates']} static "
        "candidate sites observed; not observed (not measured, NOT clean):"
    )
    for site in cov["not_observed"]:
        print(f"  - {site}")
    if result.get("error"):
        print(f"error: {result['error']}")
    if args.out:
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    clean = (
        not result["ungated_sites"]
        and result["integrity"]["ledger_complete"]
        and all(v["verdict"] == "gated" for v in result["surfaces"].values())
    )
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
