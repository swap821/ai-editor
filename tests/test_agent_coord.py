"""Tests for the shared Claude/Codex/Kimi coordination control plane."""
from __future__ import annotations

import json
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

import agent_coord


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "coord@example.test"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Coord Test"], cwd=path, check=True
    )
    (path / "tracked.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=path, check=True, capture_output=True)
    return path


@pytest.fixture()
def conn(tmp_path: Path):
    connection = agent_coord._connect(tmp_path / "coordination.db")
    yield connection
    connection.close()


def test_routes_work_with_equal_50_50_priority(conn) -> None:
    coding = agent_coord.create_task(conn, "code-1", "Implement parser", "implementation")
    policy = agent_coord.create_task(conn, "policy-1", "Review policy", "policy")
    security = agent_coord.create_task(conn, "security-1", "Threat model API", "security")
    testing = agent_coord.create_task(conn, "testing-1", "Test parser", "testing")
    override = agent_coord.create_task(
        conn, "override-1", "Implement parser", "implementation", builder_override="claude"
    )

    assert coding["builder"] == "codex"
    assert coding["reviewer"] == "claude"
    assert policy["builder"] == "claude"
    assert policy["reviewer"] == "codex"
    assert security["builder"] == "kimi"
    assert security["reviewer"] == "codex"
    assert testing["builder"] == "codex"
    assert testing["reviewer"] == "kimi"
    assert override["builder"] == "claude"
    assert override["reviewer"] == "kimi"
    inferred = agent_coord.create_task(conn, "inferred-1", "Threat model API auth", None)
    assert inferred["builder"] == "kimi"
    assert inferred["reviewer"] == "claude"


def test_either_agent_can_review_the_other_at_any_time(conn, repo: Path) -> None:
    first = agent_coord.create_task(conn, "first", "Build feature", "implementation")
    agent_coord.claim(conn, "first", first["builder"], "builder", root=repo)
    first_review = agent_coord.claim(conn, "first", first["reviewer"], "reviewer", root=repo)

    assert first_review == {
        "task_id": "first",
        "agent": "claude",
        "role": "reviewer",
        "read_only": True,
    }
    agent_coord.release(conn, "first", first["builder"], root=repo)

    second = agent_coord.create_task(conn, "second", "Review architecture", "architecture")
    agent_coord.claim(conn, "second", second["builder"], "builder", root=repo)
    second_review = agent_coord.claim(
        conn, "second", second["reviewer"], "reviewer", root=repo
    )

    assert second_review == {
        "task_id": "second",
        "agent": "codex",
        "role": "reviewer",
        "read_only": True,
    }


def test_one_writer_lease_and_dirty_adoption_are_fail_closed(conn, repo: Path) -> None:
    agent_coord.create_task(conn, "first", "Build feature", "implementation")
    agent_coord.create_task(conn, "second", "Review architecture", "architecture")
    claimed = agent_coord.claim(conn, "first", "codex", "builder", root=repo)

    assert claimed["agent"] == "codex"
    with pytest.raises(agent_coord.CoordinationError, match="held by codex"):
        agent_coord.claim(
            conn, "second", "claude", "builder", root=repo, override_routing=True
        )
    with pytest.raises(agent_coord.CoordinationError, match="for first"):
        agent_coord.claim(
            conn, "second", "codex", "builder", root=repo, override_routing=True
        )

    conn.execute("DELETE FROM leases")
    conn.commit()
    (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(agent_coord.CoordinationError, match="adopt-dirty"):
        agent_coord.claim(conn, "second", "claude", "builder", root=repo)
    assert agent_coord.claim(
        conn,
        "second",
        "claude",
        "builder",
        root=repo,
        adopt_dirty=True,
    )["agent"] == "claude"


def test_handoff_is_hash_pinned_and_stale_verdict_is_refused(conn, repo: Path) -> None:
    agent_coord.create_task(conn, "task", "Implement feature", "implementation")
    agent_coord.claim(conn, "task", "codex", "builder", root=repo)
    (repo / "tracked.txt").write_text("implemented\n", encoding="utf-8")
    handoff = agent_coord.handoff(
        conn, "task", "codex", "claude", "ready", "focused tests pass", root=repo
    )

    approved = agent_coord.record_verdict(
        conn, "task", "claude", "approve", "looks correct", root=repo
    )
    assert approved["snapshot"] == handoff["snapshot"]

    (repo / "tracked.txt").write_text("changed after review\n", encoding="utf-8")
    with pytest.raises(agent_coord.CoordinationError, match="changed after handoff"):
        agent_coord.record_verdict(
            conn, "task", "claude", "approve", "stale approval", root=repo
        )


def test_builder_cannot_be_their_own_reviewer(conn, repo: Path) -> None:
    agent_coord.create_task(conn, "task", "Implement feature", "implementation")
    agent_coord.claim(conn, "task", "codex", "builder", root=repo)

    with pytest.raises(agent_coord.CoordinationError, match="independent reviewer"):
        agent_coord.handoff(
            conn, "task", "codex", "codex", "ready", "tests pass", root=repo
        )
    with pytest.raises(agent_coord.CoordinationError, match="cannot review"):
        agent_coord.claim(
            conn, "task", "codex", "reviewer", root=repo, override_routing=True
        )


def test_messages_create_agent_inboxes(conn) -> None:
    agent_coord.create_task(conn, "task", "Implement feature", "mixed")
    message_id = agent_coord.send_message(
        conn, "task", "codex", "claude", "question", "Review the trust boundary"
    )

    unread = agent_coord.inbox(conn, "claude", unread_only=True, mark_read=True)

    assert unread[0]["id"] == message_id
    assert unread[0]["body"] == "Review the trust boundary"
    assert agent_coord.inbox(conn, "claude", unread_only=True) == []
    with pytest.raises(agent_coord.CoordinationError, match="distinct"):
        agent_coord.send_message(conn, "task", "codex", "codex", "note", "self")


def test_brief_combines_writer_state_and_unread_inbox(conn, repo: Path) -> None:
    agent_coord.create_task(conn, "task", "Implement feature", "implementation")
    agent_coord.claim(conn, "task", "codex", "builder", root=repo)
    agent_coord.send_message(conn, "task", "codex", "claude", "question", "Review this")

    result = agent_coord.brief(conn, "claude", root=repo)

    assert result["coordination"]["active_writer"]["agent"] == "codex"
    assert result["inbox"][0]["body"] == "Review this"


def test_release_requires_clean_tree_unless_explicitly_allowed(conn, repo: Path) -> None:
    agent_coord.create_task(conn, "task", "Implement feature", "implementation")
    agent_coord.claim(conn, "task", "codex", "builder", root=repo)
    (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(agent_coord.CoordinationError, match="use handoff"):
        agent_coord.release(conn, "task", "codex", root=repo)

    assert agent_coord.release(
        conn, "task", "codex", allow_dirty=True, root=repo
    )["status"] == "queued"


def test_wrong_agent_cannot_heartbeat_or_release_writer_lease(conn, repo: Path) -> None:
    agent_coord.create_task(conn, "task", "Implement feature", "implementation")
    agent_coord.claim(conn, "task", "codex", "builder", root=repo)

    with pytest.raises(agent_coord.CoordinationError, match="does not hold"):
        agent_coord.heartbeat(conn, "claude")
    with pytest.raises(agent_coord.CoordinationError, match="active writer"):
        agent_coord.release(conn, "task", "claude", root=repo)

    assert agent_coord.status(conn, root=repo)["active_writer"]["agent"] == "codex"


def test_expired_lease_is_removed_from_status(conn, repo: Path) -> None:
    agent_coord.create_task(conn, "task", "Implement feature", "implementation")
    agent_coord.claim(conn, "task", "codex", "builder", root=repo)
    conn.execute(
        "UPDATE leases SET expires_at = ?",
        (agent_coord._iso(agent_coord._now() - timedelta(minutes=1)),),
    )
    conn.commit()

    assert agent_coord.status(conn, root=repo)["active_writer"] is None


def test_messages_are_bounded_and_tasks_must_exist(conn) -> None:
    agent_coord.create_task(conn, "task", "Implement feature", "implementation")

    with pytest.raises(agent_coord.CoordinationError, match="required"):
        agent_coord.send_message(conn, "task", "codex", "claude", "note", "")
    with pytest.raises(agent_coord.CoordinationError, match="8000"):
        agent_coord.send_message(conn, "task", "codex", "claude", "note", "x" * 8001)
    with pytest.raises(agent_coord.CoordinationError, match="unknown task"):
        agent_coord.send_message(conn, "missing", "codex", "claude", "note", "hello")


def test_cli_lifecycle_uses_the_same_control_plane(tmp_path: Path, capsys) -> None:
    db = tmp_path / "coordination.db"
    base = ["--db", str(db)]

    assert agent_coord.main([*base, "init"]) == 0
    assert agent_coord.main(
        [*base, "route", "task", "Implement coordination"]
    ) == 0
    assert agent_coord.main(
        [
            *base,
            "claim",
            "task",
            "--agent",
            "codex",
            "--role",
            "builder",
            "--adopt-dirty",
        ]
    ) == 0
    assert agent_coord.main(
        [
            *base,
            "message",
            "task",
            "--from",
            "codex",
            "--to",
            "claude",
            "--kind",
            "question",
            "--body",
            "Review this",
        ]
    ) == 0
    capsys.readouterr()
    assert agent_coord.main([*base, "brief", "--agent", "claude"]) == 0
    brief_payload = json.loads(capsys.readouterr().out)
    assert brief_payload["agent"] == "claude"
    assert agent_coord.main(
        [
            *base,
            "handoff",
            "task",
            "--from",
            "codex",
            "--to",
            "claude",
            "--summary",
            "ready",
            "--evidence",
            "tests pass",
        ]
    ) == 0
    assert agent_coord.main(
        [
            *base,
            "verdict",
            "task",
            "--reviewer",
            "claude",
            "--verdict",
            "approve",
            "--summary",
            "no blockers",
        ]
    ) == 0
    assert agent_coord.main([*base, "status"]) == 0


def test_cli_returns_error_for_unknown_task(tmp_path: Path, capsys) -> None:
    result = agent_coord.main(
        [
            "--db",
            str(tmp_path / "coordination.db"),
            "claim",
            "missing",
            "--agent",
            "codex",
            "--role",
            "builder",
        ]
    )

    assert result == 2
    assert "unknown task" in capsys.readouterr().err
