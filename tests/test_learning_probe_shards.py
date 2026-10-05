"""Plan Phase 8b: the mutation probe shards, so CI can run it as a matrix.

The full probe is ~650 mutations and hours of pytest -- past a hosted runner's
six-hour limit run serially. `--shard I/N` splits the selection; these pin
that N shards are the WHOLE selection, each entry exactly once, and that a
malformed spec refuses instead of running some guess at a shard.
"""

from __future__ import annotations

import json

import pytest

from scripts import learning_mutation_probe as probe


def _entries(count: int) -> list[probe.Entry]:
    return [
        probe.Entry(id=f"t:{i}", file="guard.py", old=f"o{i}", new=f"n{i}", tests=["t"])
        for i in range(count)
    ]


@pytest.mark.parametrize("n", [1, 2, 3, 5, 7])
def test_n_shards_are_the_whole_selection_each_entry_once(n: int) -> None:
    entries = _entries(23)
    shards = [probe.shard(entries, f"{i}/{n}") for i in range(n)]
    ids = [e.id for s in shards for e in s]
    assert sorted(ids) == sorted(e.id for e in entries)
    assert len(ids) == len(set(ids))
    assert max(len(s) for s in shards) - min(len(s) for s in shards) <= 1


@pytest.mark.parametrize("spec", ["3", "a/b", "3/3", "-1/2", "0/0", "1/", "/2"])
def test_a_malformed_shard_refuses(spec: str) -> None:
    with pytest.raises(probe.ProbeError):
        probe.shard(_entries(5), spec)


def test_the_cli_runs_only_its_shard(monkeypatch, capsys) -> None:
    entries = _entries(5)
    seen: list[list[str]] = []
    monkeypatch.setattr(probe, "load", lambda path=probe.CATALOGUE: entries)
    monkeypatch.setattr(probe, "load_guards", lambda path=probe.CATALOGUE: {})

    def coverage(selected, killed, guards):
        seen.append([e.id for e in selected])
        return {
            "attacked": 0,
            "decision_points": 0,
            "guard_functions": 0,
            "missing_guards": [],
            "unattacked": [],
        }

    monkeypatch.setattr(probe, "coverage", coverage)
    assert probe.main(["--shard", "1/2", "--coverage"]) == 0
    assert seen == [["t:1", "t:3"]]
    json.loads(capsys.readouterr().out.splitlines()[0])
