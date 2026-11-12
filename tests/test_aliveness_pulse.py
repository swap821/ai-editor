"""The aliveness pulse (organ 52): which parts of GAGOS do real work (2026-11-12).

The operator asked "are we using SWARM infra... there can be many things like
this"; measured, most organs had last run in a proof harness or never. The pulse
makes that a daily measurement in GAGOS's own report. Pinned here: every organ
of the ledger is declared (a new one cannot go silent unseen); statuses come
from each part's own stores and the cortex bus, read-only; a workshop writer
that edits a swarm file is not a swarm run.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aios.application.observability import aliveness
from aios.application.observability.aliveness import PARTS, Part
from tools import gagos_daily as tool

NOW = datetime(2026, 11, 12, 16, 0, tzinfo=timezone.utc)
LEDGER = (
    Path(__file__).resolve().parents[1] / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
)


def _stamp(days: float) -> str:
    return (NOW - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _db(path: Path, ddl: str, rows: list[tuple] = ()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(ddl)
    if rows:
        marks = ",".join("?" * len(rows[0]))
        table = ddl.split()[2]
        con.executemany(f"insert into {table} values ({marks})", rows)
    con.commit()
    con.close()


def _worker(mission: str, contract: str, days: float) -> tuple:
    payload = {
        "missionId": mission,
        "payload": {"strategy": "code", "contract_digest": contract},
    }
    return ("worker.requested", _stamp(days), json.dumps(payload))


def _data(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    _db(
        data / "a.db",
        "create table spend (id int, created_at text)",
        [(1, _stamp(0.5))],
    )
    _db(
        data / "b.db",
        "create table missions (id int, updated_at text)",
        [(1, _stamp(24))],
    )
    _db(data / "c.db", "create table skill_trails (id int, ts text)", [(1, _stamp(9))])
    _db(data / "d.db", "create table deliberation_records (id int, created_at text)")
    _db(data / "e.db", "create table playbook (rule text)", [("keep it small",)])
    _db(
        data / "cortex_bus.db",
        "create table cortex_events (event_type text, created_at text, payload text)",
        [
            ("turn.completed", _stamp(13), "{}"),
            _worker(
                "gagos-2026-11-12T15",
                "workshop-writer:gagos:m:aios/agents/swarm_patterns.py",
                0.1,
            ),
            _worker("maint-1", "code-repair:maint-1", 30),
        ],
    )
    # A backup of a store is not the store: it never counts.
    _db(
        data / "backups" / "x.db",
        "create table approval_grants (id int, created_at text)",
        [(1, _stamp(0))],
    )
    return data


def _reading(data: Path, part: Part):
    seen = aliveness.scan(data, now=NOW)
    return aliveness.read(part, seen, now=NOW)


def test_every_organ_of_the_ledger_is_declared_once_by_its_own_name() -> None:
    ledger = {
        o["organ_id"]: o["name"] for o in json.loads(LEDGER.read_text(encoding="utf-8"))
    }
    organs = [p for p in PARTS if p.key.startswith("organ-")]
    ids = [int(p.key.split("-")[1]) for p in organs]
    assert sorted(ids) == sorted(ledger), "every organ, each exactly once"
    for part, organ_id in zip(organs, ids):
        number, name = part.name.split(" ", 1)
        assert int(number) == organ_id
        assert ledger[organ_id].startswith(name), (organ_id, ledger[organ_id], name)


def test_every_part_is_measurable_or_says_why_not() -> None:
    for part in PARTS:
        assert part.kind in ("", aliveness.GUARD, aliveness.FACE, aliveness.EVALUATION)
        measured = part.tables or part.events or part.workers
        assert bool(measured) != bool(part.kind), part.key


def test_statuses_come_from_each_parts_own_evidence(tmp_path) -> None:
    data = _data(tmp_path)
    assert _reading(data, Part("p", "spend", tables=("spend",))).status == "live"
    assert (
        _reading(data, Part("p", "trails", tables=("skill_trails",))).status == "recent"
    )
    assert _reading(data, Part("p", "missions", tables=("missions",))).status == "stale"
    assert (
        _reading(data, Part("p", "turns", events=("turn.completed",))).status
        == "recent"
    )
    never = _reading(data, Part("p", "dissent", tables=("deliberation_records",)))
    assert never.status == "never"
    assert never.why == "its stores have never held a row"
    undated = _reading(data, Part("p", "playbook", tables=("playbook",)))
    assert undated.status == "undated"
    assert "1 rows in playbook" in undated.why
    guard = _reading(data, Part("p", "stop", kind=aliveness.GUARD))
    assert guard.status == "guard"


def test_a_backup_never_counts_as_the_store(tmp_path) -> None:
    seen = aliveness.scan(_data(tmp_path), now=NOW)
    assert "approval_grants" not in seen.tables


def test_a_workshop_writer_editing_a_swarm_file_is_not_a_swarm_run(tmp_path) -> None:
    seen = aliveness.scan(_data(tmp_path), now=NOW)
    assert set(seen.workers) == {aliveness.WORKSHOP, aliveness.MISSION}
    swarm = Part("swarm", "Swarm", tables=(), workers=(aliveness.SWARM,))
    assert aliveness.read(swarm, seen, now=NOW).status == "never"


def test_worker_sources() -> None:
    def source(mission: str, contract: str, strategy: str = "code") -> str:
        payload = {
            "missionId": mission,
            "payload": {"strategy": strategy, "contract_digest": contract},
        }
        return aliveness.worker_source(json.dumps(payload))

    assert source("goal-x", "swarm-leg:goal-x:scout:read_file") == aliveness.SWARM
    assert source("goal-x", "anything", strategy="swarm") == aliveness.SWARM
    assert (
        source("gagos-2026-11-12T15", "workshop-writer:gagos:m:SwarmHUD.test.tsx")
        == aliveness.WORKSHOP
    )
    assert source("maint-3b41d3d6", "code-repair") == aliveness.MISSION
    assert aliveness.worker_source("not json") == "other"


def test_the_scan_changes_nothing(tmp_path) -> None:
    data = _data(tmp_path)
    before = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
    aliveness.pulse(data, now=NOW)
    after = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
    assert after == before


def test_report_lines_count_and_name_the_silent(tmp_path) -> None:
    readings = aliveness.pulse(_data(tmp_path), now=NOW)
    lines = aliveness.report_lines(readings)
    assert lines[0].startswith("**Aliveness**")
    assert "never" in lines[0] and "guard 7" in lines[0]
    never = next(line for line in lines if line.startswith("- never ran:"))
    assert "39 Multi-Model Deliberation and Dissent" in never
    stale = next(line for line in lines if line.startswith("- silent over 14 days:"))
    assert "10 Mission Authority (last 2026-10-19)" in stale


def test_the_daily_report_carries_the_pulse_scrubbed(tmp_path) -> None:
    led = tool.DailyLedger(tmp_path / "ledger.db")
    text = tool.report(
        led,
        aliveness=["**Aliveness**: live 1.", "- never ran: AKIAIOSFODNN7EXAMPLE", ""],
        scrub=lambda s: s.replace("AKIAIOSFODNN7EXAMPLE", "[key]"),
    )
    assert "**Aliveness**: live 1." in text
    assert "- never ran: [key]" in text
    assert "AKIAIOSFODNN7EXAMPLE" not in text
    assert "**Aliveness**" not in tool.report(led)


def test_a_pulse_that_cannot_be_measured_says_so(monkeypatch) -> None:
    def broken(_data_dir, **_kw):
        raise OSError("disk gone")

    monkeypatch.setattr(aliveness, "pulse", broken)
    (line, blank) = tool.aliveness_lines()
    assert line == "**Aliveness**: not measured (OSError: disk gone)"
    assert blank == ""
