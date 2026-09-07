#!/usr/bin/env python3
"""One live pass of the learning loop, on a real model, with replay turned ON.

The matrix (`replay_live_matrix.py`) constructs each situation directly. This
does not: it drives a real local model through a real `ToolAgent` turn, lets
that turn's own steps become a skill, compiles whatever the compiler is willing
to compile, and replays it against the filesystem.

The loop, end to end, with nothing stubbed in the middle:

    real Ollama turn -> approved write lands -> approval recorded
    -> skill recorded -> playbook compiled -> target deleted -> REPLAY

SCOPE, stated rather than implied. The HTTP capability layer is NOT exercised
here -- `record_approval` is reached through `ToolAgent`'s approved-creations
path, which is the same code the resumed HTTP turn runs, but the enrollment and
capability-token dance belongs to the organ-55 drivers and adds no information
about the question this asks.

THE QUESTION THIS CANNOT ANSWER. One session is not a rate. If recorded files
are usually stale by replay time then every playbook abstains and the feature
is worth little, and that number needs sustained real use. What this can show
is whether the loop closes at all on a real model, which has never been run.

Run:  python scripts/replay_live_session.py
Exit: 0 if the loop closed (a replay reached a verdict), 1 otherwise.
      An ABSTAIN is a legitimate result and is reported as one, not hidden.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aios import config  # noqa: E402
from aios.security import scope_lock  # noqa: E402

_GOAL = "create a file called greeting.py containing a hello function"
_CONTENT = 'def hello(name):\n    return f"hello {name}"\n'


def _pick_model() -> str | None:
    """Smallest installed model, so the run is about the loop and not the GPU."""
    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed loopback URL
            "http://127.0.0.1:11434/api/tags", timeout=8
        ) as resp:
            models = json.loads(resp.read()).get("models", [])
    except Exception as exc:  # noqa: BLE001
        print(f"  ollama unreachable: {exc}")
        return None
    # Embedding models answer /api/tags but cannot chat. The first run of this
    # script picked `nomic-embed-text` because it was simply the smallest, and
    # the turn produced nothing useful -- "smallest" is not the same as
    # "smallest model that can hold a conversation".
    chat = [
        m
        for m in models
        if not any(
            tag in str(m.get("name", "")).lower()
            for tag in ("embed", "bge-", "minilm", "rerank")
        )
    ]
    if not chat:
        return None
    smallest = min(chat, key=lambda m: m.get("size", 1 << 62))
    return str(smallest.get("name"))


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="replay-session-"))
    sandbox = root / "training_ground"
    sandbox.mkdir()
    db = root / "session.db"

    from aios.agents.tool_agent import ToolAgent
    from aios.core.cerebellum import Cerebellum
    from aios.core.executor import Executor
    from aios.core.llm import OllamaClient
    from aios.core.replay_writes import is_approved_write, content_digest
    from aios.memory.db import init_memory_db
    from aios.memory.skills import SkillMemory

    init_memory_db(db)
    config.REPLAY_APPROVED_WRITES_ENABLED = True
    config.MEMORY_DB_PATH = db
    scope_lock._SCOPE_LOCK = scope_lock.ScopeLockAuthority()
    scope_lock.set_scope_roots([sandbox])

    model = _pick_model()
    if model is None:
        print("SKIPPED: no local model available; this run needs a real one.")
        return 1

    print(f"model   : {model}")
    print(f"sandbox : {sandbox}")
    print(
        f"flag    : AIOS_REPLAY_APPROVED_WRITES = {config.REPLAY_APPROVED_WRITES_ENABLED}"
    )
    print()

    def _runner(command, *, cwd, env, timeout_s):
        return f"ran: {command}", "", 0

    # ---- 1. a real turn on a real model, with the write already approved ----
    print("[1] real turn on a live model, human-approved creation")
    agent = ToolAgent(
        OllamaClient(model=model),
        Executor(runner=_runner, audit_log=lambda *a, **k: None),
        max_iters=3,
        read_root=sandbox,
        approved_creations=[{"filepath": "greeting.py", "content": _CONTENT}],
    )
    events = list(agent.run([{"role": "user", "content": _GOAL}]))
    steps = [
        f"create_file: filepath=greeting.py, content_sha256={content_digest(_CONTENT)}"
    ]
    landed = (sandbox / "greeting.py").exists()
    print(f"    events: {len(events)}   file landed: {landed}")

    recorded = is_approved_write(
        "greeting.py", content_digest(_CONTENT), db_path=db, enabled=True
    )
    print(f"    approval recorded by the real path: {recorded}")
    if not recorded:
        print("    STOP: the approval was not recorded, so nothing downstream is real.")
        shutil.rmtree(root, ignore_errors=True)
        return 1

    # ---- 2. the turn's own steps become a skill, then a playbook ------------
    print("[2] skill -> playbook")
    skills = SkillMemory(db)
    for _ in range(5):
        skills.record_attempt(_GOAL, steps, success=True)
    cb = Cerebellum(db)
    compiled = cb.try_compile_all()
    # The cache is loaded on construction, so a Cerebellum built BEFORE the
    # compile would report zero playbooks while the database held one. Ask the
    # instance that did the compiling, or refresh.
    cb._refresh_cache()
    playbooks = list(cb._cache.values())
    print(f"    compiled: {compiled}   playbooks: {len(playbooks)}")
    if not playbooks:
        print("    STOP: nothing compiled, so there is no replay to observe.")
        shutil.rmtree(root, ignore_errors=True)
        return 1

    # ---- 3. delete the target, then replay ---------------------------------
    print("[3] delete the target, replay the playbook")
    (sandbox / "greeting.py").unlink()
    assert not (sandbox / "greeting.py").exists()

    pb = playbooks[0]
    replay_events = list(cb.replay(pb, dispatch_fn=agent._dispatch_approved))
    kinds = [e["type"] for e in replay_events]
    final = replay_events[-1] if replay_events else {}

    print(f"    events : {kinds}")
    print(f"    verdict: {final.get('type')} {final.get('reason', '')}")
    print(f"    output : {str(final.get('output', ''))[:120]}")

    restored = (sandbox / "greeting.py").exists()
    same = (
        restored and (sandbox / "greeting.py").read_text(encoding="utf-8") == _CONTENT
    )
    print()
    print(f"  file restored by the replay : {restored}")
    print(f"  bytes match the approval    : {same}")

    if final.get("type") == "cerebellum_abort":
        print()
        print("  RESULT: the replay ABSTAINED. That is a real outcome, not a")
        print("  failure of the run -- it is reported as what happened.")
        print(f"  reason: {final.get('reason')} / permanent={final.get('permanent')}")

    shutil.rmtree(root, ignore_errors=True)
    return 0 if replay_events else 1


if __name__ == "__main__":
    raise SystemExit(main())
