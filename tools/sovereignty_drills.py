"""Sovereignty drills: is GAGOS local-first when it matters? Measured live.

    python tools/sovereignty_drills.py                 # all drills
    python tools/sovereignty_drills.py --only offline  # one
    python tools/sovereignty_drills.py --out report.json

Each drill runs in its own child process on a throwaway data directory,
through the REAL app (the red-team reel's isolated Harness: real routes, real
router, real failover, real privacy filter) with the REAL local model in
Ollama's seat. Only the cloud transport is controlled:

* **offline**   the child's network is cut at the socket (loopback only) and
                Bedrock is a real client that really tries the network. The
                turn must still be answered -- by the local model.
* **failover**  Bedrock is the real client over a transport that throttles.
                The turn must fall back to the local model. If the router never
                tried the cloud first, nothing was measured: NOT_REACHED.
* **privacy**   Bedrock is the real client -- its privacy filter included --
                over a recording transport, asked for explicitly. What the
                filter guarantees to keep home (a credential, a local file
                path) must not be in what the transport got. The agent's system
                prompt is sent, scrubbed; the report records it.

Cloud routing for ``auto`` is OFF by default (``AIOS_ROUTER_CLOUD_TASKS`` is
empty), so offline and failover run with it ON -- the configuration where they
matter -- and the report says so. Verdicts: pass | fail | not_reached | error.
A drill whose model never answered is an error, never a pass.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DRILLS = ("offline", "failover", "privacy")
#: The built-in runtime profile in which cloud is allowed AND preferred for
#: coding (aios/runtime/profiles.json). Routing policy comes from the runtime
#: profile, not from AIOS_ROUTER_CLOUD_TASKS (found 2026-10-11).
CLOUD_PRIMARY_PROFILE = "autonomous"
#: A coding question, so the task is one the profile lets leave the machine.
QUESTION = (
    "Explain this code in one short sentence, without using any tools: print('Paris')"
)
PRIVACY_QUESTION_PREFIX = "Summarise this note in one line"
PASS, FAIL, NOT_REACHED, ERROR = "pass", "fail", "not_reached", "error"
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


# --------------------------------------------------------------------------- #
# Judging -- pure, so it is tested without a model
# --------------------------------------------------------------------------- #


def judge(drill: str, obs: Mapping[str, Any]) -> tuple[str, str]:
    """``(verdict, why)`` for one drill's observation."""
    if obs.get("error"):
        return ERROR, str(obs["error"])
    if obs.get("status") != 200:
        return ERROR, f"the turn was refused: HTTP {obs.get('status')}"
    served = obs.get("served_by") or []
    answer = str(obs.get("answer") or "").strip()
    attempts = int(obs.get("cloud_attempts") or 0)
    if drill in ("offline", "failover"):
        if not answer:
            where = (
                "the turn reached the local model, which gave no answer "
                f"({'; '.join(obs.get('stream_errors') or [])[:160] or 'no text'})"
                if served and served[-1] == "ollama"
                else f"no answer reached the operator (served_by={served})"
            )
            return FAIL, where
        if not served or served[-1] != "ollama":
            return (
                FAIL,
                f"the turn was served by {served or 'nothing'}, not the local model",
            )
        if drill == "failover" and attempts == 0:
            return NOT_REACHED, (
                "the router never tried the cloud first, so no failover happened "
                "to measure"
            )
        return PASS, (
            f"answered by the local model; cloud attempts {attempts}"
            + (
                f", blocked at the socket: {len(obs.get('blocked') or [])}"
                if drill == "offline"
                else ""
            )
        )
    if drill == "privacy":
        if attempts == 0:
            return (
                NOT_REACHED,
                "the cloud transport was never called: nothing left to check",
            )
        found = [
            name
            for name, present in (obs.get("canaries_sent") or {}).items()
            if present
        ]
        if found:
            return FAIL, f"reached the cloud transport unredacted: {found}"
        return (
            PASS,
            f"{attempts} cloud request(s); no credential and no local path in any"
            + (
                " (the agent's system prompt is sent, scrubbed)"
                if obs.get("system_prompt_sent")
                else ""
            ),
        )
    return ERROR, f"unknown drill {drill!r}"


# --------------------------------------------------------------------------- #
# Inside the child
# --------------------------------------------------------------------------- #


class _Throttled(Exception):
    pass


class _Transport:
    """A Bedrock runtime transport the drill controls. Records every request."""

    def __init__(self, *, fail: bool) -> None:
        self.fail = fail
        self.requests: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        if self.fail:
            from botocore.exceptions import ClientError

            raise ClientError(
                {
                    "Error": {
                        "Code": "ThrottlingException",
                        "Message": "drill: throttled",
                    }
                },
                "Converse",
            )
        return {
            "output": {
                "message": {"role": "assistant", "content": [{"text": "Paris."}]}
            },
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
        }

    def converse_stream(self, **kwargs: Any) -> dict[str, Any]:
        """The path a cloud agent turn actually takes (stream_chat_with_tools)."""
        self.requests.append(kwargs)
        if self.fail:
            from botocore.exceptions import ClientError

            raise ClientError(
                {
                    "Error": {
                        "Code": "ThrottlingException",
                        "Message": "drill: throttled",
                    }
                },
                "ConverseStream",
            )
        return {
            "stream": [
                {
                    "contentBlockDelta": {
                        "contentBlockIndex": 0,
                        "delta": {"text": "Paris."},
                    }
                },
                {"messageStop": {"stopReason": "end_turn"}},
            ]
        }


class _NoDiscovery:
    def list_foundation_models(self, **kwargs: Any) -> dict[str, Any]:
        return {"modelSummaries": []}


class _SocketCut:
    """Cut this process off the network: only loopback may connect."""

    def __init__(self) -> None:
        self.blocked: list[str] = []
        self._connect = socket.socket.connect
        self._connect_ex = socket.socket.connect_ex
        self._getaddrinfo = socket.getaddrinfo

    @staticmethod
    def _host(address: Any) -> str:
        return str(address[0] if isinstance(address, tuple) else address)

    def install(self) -> None:
        cut = self

        def connect(sock, address):  # type: ignore[no-untyped-def]
            host = cut._host(address)
            if host not in _LOOPBACK:
                cut.blocked.append(host)
                raise ConnectionRefusedError(f"drill: network cut ({host})")
            return cut._connect(sock, address)

        def connect_ex(sock, address):  # type: ignore[no-untyped-def]
            host = cut._host(address)
            if host not in _LOOPBACK:
                cut.blocked.append(host)
                return 111
            return cut._connect_ex(sock, address)

        def getaddrinfo(host, *args, **kwargs):  # type: ignore[no-untyped-def]
            if host is not None and str(host) not in _LOOPBACK:
                cut.blocked.append(str(host))
                raise socket.gaierror(f"drill: network cut ({host})")
            return cut._getaddrinfo(host, *args, **kwargs)

        socket.socket.connect = connect  # type: ignore[method-assign]
        socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
        socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]


def _turn(h: Any, text: str, model_id: str) -> dict[str, Any]:
    """One real /api/generate turn; the frames the drills read."""
    response = h.client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": text}]}],
            "sessionId": f"drill-{secrets.token_hex(4)}",
            "modelId": model_id,
        },
    )
    served: list[str] = []
    answer: list[str] = []
    errors: list[str] = []
    event = ""
    for line in response.text.splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            try:
                data = json.loads(line.split(":", 1)[1].strip())
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            if event == "route" and data.get("provider"):
                served.append(str(data["provider"]))
            elif event in ("text_chunk", "text") and isinstance(data.get("text"), str):
                answer.append(data["text"])
            elif event == "error":
                errors.append(str(data.get("text") or data)[:200])
    return {
        "status": response.status_code,
        "served_by": served,
        "answer": "".join(answer)[:400],
        "stream_errors": errors,
    }


def run_child(drill: str, root: Path, out: Path) -> int:
    from tools import learning_redteam_runner as lrt

    obs: dict[str, Any] = {"drill": drill}
    h = None
    try:
        from aios.api.main import get_bedrock_client
        from aios.core.bedrock import BedrockClient

        cut: Optional[_SocketCut] = None
        transport: Optional[_Transport] = None
        model = os.environ.get("AIOS_DRILL_CLOUD_MODEL", "deepseek.v3.2")
        if drill == "offline":
            cut = _SocketCut()
            bedrock = BedrockClient(
                model=model, region="ap-south-1", ctrl_client=_NoDiscovery()
            )
        else:
            transport = _Transport(fail=(drill == "failover"))
            bedrock = BedrockClient(
                model=model,
                region="ap-south-1",
                client=transport,
                ctrl_client=_NoDiscovery(),
            )
        h = lrt.Harness(root)
        h.app.dependency_overrides[get_bedrock_client] = lambda: bedrock
        if cut is not None:
            cut.install()
        if drill == "privacy":
            key = "AKIA" + "".join(
                secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(16)
            )
            path = (
                r"C:\Users\drill-operator\secrets\vault-"
                + secrets.token_hex(3)
                + ".txt"
            )
            text = (
                f"{PRIVACY_QUESTION_PREFIX}: my aws_access_key_id={key} and the "
                f"backup lives at {path}."
            )
            # Any explicit id that is not ollama./gemini./openai./anthropic.
            # is a Bedrock pick: the real BedrockClient serves it.
            obs.update(_turn(h, text, model))
            sent = (
                json.dumps([r for r in transport.requests], default=str)
                if transport
                else ""
            )
            # What the privacy filter guarantees never leaves: credentials and
            # local paths. The agent's system prompt IS sent (a cloud agent
            # needs its instructions), scrubbed -- recorded, not judged.
            obs["canaries_sent"] = {
                "access_key": key in sent,
                "local_path": "drill-operator" in sent,
            }
            obs["system_prompt_sent"] = "embedded in an IDE workspace" in sent
        else:
            obs.update(_turn(h, QUESTION, "auto"))
        obs["cloud_attempts"] = (
            len(transport.requests)
            if transport is not None
            else len([b for b in (cut.blocked if cut else []) if "amazonaws" in b])
        )
        if cut is not None:
            obs["blocked"] = sorted(set(cut.blocked))
        obs["seat"] = getattr(h.chat, "model_id", None)
        obs["model_errors"] = list(getattr(h.chat, "errors", ()))
        if obs["model_errors"] and not obs.get("answer"):
            obs["error"] = "the local model did not answer: " + "; ".join(
                obs["model_errors"][:2]
            )
    except Exception as exc:  # noqa: BLE001 - reported as an error, never as a verdict
        obs["error"] = f"{type(exc).__name__}: {exc}"[:400]
    finally:
        if h is not None:
            h.close()
    out.write_text(json.dumps(obs, default=str), encoding="utf-8")
    return 0


# --------------------------------------------------------------------------- #
# The parent
# --------------------------------------------------------------------------- #


def _env(root: Path, drill: str) -> dict[str, str]:
    from aios import config
    from tools import learning_redteam_runner as lrt

    env = lrt.child_environment(root)
    env[lrt.BEHAVIOURAL_MODEL_ENV] = "ollama:" + os.environ.get(
        "AIOS_LLM_MODEL", config.LLM_MODEL
    )
    # Drills never hold a real cloud key: the transport is the drill's, or
    # (offline) a real client whose network is cut. A placeholder key makes the
    # offline client reach for the network rather than stop at "no creds".
    for name in list(env):
        if name.startswith(
            ("AWS_", "AIOS_OPENAI", "AIOS_ANTHROPIC", "GEMINI", "GOOGLE_API")
        ):
            env.pop(name)
    env["AWS_BEARER_TOKEN_BEDROCK"] = "drill-placeholder-not-a-key"
    env["AIOS_BEDROCK_REGION"] = "ap-south-1"
    if drill in ("offline", "failover"):
        # Cloud-PRIMARY: the profile that allows AND prefers cloud for coding.
        # Under local-first (the default) auto never leaves the machine, and
        # under operator local is still preferred -- so a cut network or a
        # throttling provider only matters here, and only here is measured.
        env["AIOS_RUNTIME_PROFILE"] = CLOUD_PRIMARY_PROFILE
        # And the constitution, which is the CEILING once the one-law change
        # lands (operator decision 2026-10-11): the profile may only narrow
        # what the constitution allows, so the law must allow it too.
        env["AIOS_ROUTER_CLOUD_TASKS"] = "coding,reasoning"
        env["AIOS_ROUTER_PREFER_LOCAL"] = "false"
    return env


def run_drill(drill: str, timeout_s: int = 900) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="sov-drill-") as tmp:
        root = Path(tmp)
        out = root / "observation.json"
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "_child",
                    drill,
                    "--root",
                    str(root),
                    "--out",
                    str(out),
                ],
                cwd=str(REPO_ROOT),
                env=_env(root, drill),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            obs: dict[str, Any] = {"error": f"timed out after {timeout_s}s"}
        else:
            if out.is_file():
                obs = json.loads(out.read_text(encoding="utf-8"))
            else:
                obs = {
                    "error": f"child exited {proc.returncode}: {(proc.stderr or '')[-300:]}"
                }
    verdict, why = judge(drill, obs)
    return {"verdict": verdict, "why": why, "observation": obs}


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
        ).stdout.strip()
    except OSError:
        return ""


def default_report_path() -> Path:
    from aios import config

    return Path(config.DATA_DIR) / "drills" / "sovereignty.json"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")
    child = sub.add_parser("_child")
    child.add_argument("drill", choices=DRILLS)
    child.add_argument("--root", type=Path, required=True)
    child.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only", choices=DRILLS, action="append")
    parser.add_argument("--out", type=Path, default=None, help="report path")
    args = parser.parse_args(argv)
    if args.command == "_child":
        return run_child(args.drill, args.root, args.out)
    results = {}
    for drill in args.only or DRILLS:
        results[drill] = run_drill(drill)
        print(
            f"{drill:<9} {results[drill]['verdict'].upper():<12} {results[drill]['why']}",
            flush=True,
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": _commit(),
        "auto_cloud_routing_default": "local-first profile: auto never uses cloud",
        "offline_and_failover_configuration": f"runtime profile {CLOUD_PRIMARY_PROFILE!r} (cloud preferred for coding)",
        "drills": results,
    }
    path = args.out or default_report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"report: {path}")
    return 0 if all(r["verdict"] == PASS for r in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
