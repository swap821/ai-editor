"""The judged payoff verdict is recomputed from the committed trails, never
typed by hand; and a member is met only if positive AND Holm-significant (D4)."""

from __future__ import annotations

import json

from tools import judge_payoff_family as jf


def test_the_committed_verdict_is_what_the_committed_trails_say() -> None:
    committed = json.loads(jf.RESULT.read_text(encoding="utf-8"))
    recomputed = jf.judge(
        jf._load(jf.CLOUD),
        jf._load(jf.LOCAL),
        jf._load(jf.CLOUD_BASELINE),
        jf._load(jf.LOCAL_BASELINE),
    )
    assert committed == json.loads(json.dumps(recomputed))


def _stats(on_only: int, off_only: int, p: float) -> dict:
    return {
        "arms": ["on", "off"],
        "pairs": 50,
        "samples": 1,
        "on_earned": on_only,
        "off_earned": off_only,
        "on_only": on_only,
        "off_only": off_only,
        "p_value": p,
    }


def _run(novel: dict, content: dict | None = None) -> dict:
    return {
        "run_id": "r",
        "corpus_sha": "c",
        "harness_sha": "h",
        "models": "m",
        "samples": 1,
        "placebo": content is not None,
        "summary": {
            "novel": novel,
            "content_novel": content or novel,
            "all": novel,
        },
        "pairs": [],
    }


def test_a_member_is_met_only_when_positive_and_holm_significant() -> None:
    base = {"pairs": []}
    strong = jf.judge(
        _run(_stats(20, 2, 0.0001), _stats(18, 3, 0.001)),
        _run(_stats(3, 2, 0.9)),
        base,
        base,
    )
    assert strong["family"]["H1-cloud"]["met"] is True
    assert strong["family"]["H1-7B"]["met"] is False
    assert strong["h1_met"] is True

    # Significant, but memory HURT: never "met".
    harmful = jf.judge(
        _run(_stats(2, 20, 0.0001), _stats(2, 20, 0.0001)),
        _run(_stats(2, 20, 0.0001)),
        base,
        base,
    )
    assert harmful["h1_met"] is False
    assert all(not m["met"] for m in harmful["family"].values())
    assert harmful["h2_harm"]["cloud"]["violated"] is True

    # Raw p under 0.05 that Holm lifts over it is not met.
    borderline = jf.judge(
        _run(_stats(10, 3, 0.03), _stats(10, 3, 0.04)),
        _run(_stats(10, 3, 0.045)),
        base,
        base,
    )
    assert borderline["family"]["H1-cloud"]["holm_p"] >= 0.05
    assert borderline["h1_met"] is False


def _d12_run(novel: dict, content: dict) -> dict:
    run = _run(novel, content)
    run["summary"]["all"] = novel
    return run


def test_the_d12_family_is_holm_over_four_members() -> None:
    """Written 2026-10-21, before the local run produced any data."""
    weak = _stats(18, 16, 1.0)
    result = jf.judge_d12(
        _d12_run(weak, _stats(21, 16, 0.72)),
        _d12_run(_stats(30, 5, 0.004), _stats(25, 8, 0.03)),
    )
    family = result["family"]
    assert set(family) == {
        "H1-cloud-D12",
        "H1c-cloud-D12",
        "H1-local-D12",
        "H1c-local-D12",
    }
    # Holm over four: the smallest p is multiplied by 4.
    assert family["H1-local-D12"]["holm_p"] == 0.016
    assert family["H1-local-D12"]["met"] is True
    assert family["H1c-local-D12"]["met"] is False, "0.03 x 3 = 0.09"
    assert family["H1-cloud-D12"]["met"] is False
    assert result["h1_met"] is True and "D12 family MET" in result["summary"]
    assert set(result["h2_harm"]) == {"cloud", "local"}


def test_a_negative_member_is_never_met_however_small_its_p() -> None:
    result = jf.judge_d12(
        _d12_run(_stats(2, 30, 0.0001), _stats(2, 30, 0.0001)),
        _d12_run(_stats(2, 30, 0.0001), _stats(2, 30, 0.0001)),
    )
    assert not any(m["met"] for m in result["family"].values())
    assert all(v["violated"] for v in result["h2_harm"].values()), "harm is seen"


def test_a_partial_d12_family_is_never_written(tmp_path, monkeypatch, capsys) -> None:
    cloud = tmp_path / "cloud.json"
    cloud.write_text(json.dumps(_d12_run(_stats(1, 1, 1.0), _stats(1, 1, 1.0))))
    monkeypatch.setattr(jf, "D12_CLOUD", cloud)
    monkeypatch.setattr(jf, "D12_LOCAL", tmp_path / "missing.json")
    monkeypatch.setattr(jf, "D12_RESULT", tmp_path / "result.json")
    assert jf.main(["--family", "d12", "--write"]) == 1
    assert not (tmp_path / "result.json").exists()
    assert "partial family is not a verdict" in capsys.readouterr().out


def test_the_d13_family_is_holm_over_two_local_members() -> None:
    """Written 2026-10-28, before the D13 run produced any data."""
    result = jf.judge_d13(_d12_run(_stats(22, 9, 0.029), _stats(20, 10, 0.099)))
    family = result["family"]
    assert set(family) == {"H1-local-D13", "H1c-local-D13"}
    # Holm over two: the smaller p is doubled.
    assert family["H1-local-D13"]["holm_p"] == 0.058
    assert family["H1-local-D13"]["met"] is False, "0.029 x 2 is not below 0.05"
    assert result["h1_met"] is False and "D13 family not met" in result["summary"]
    assert set(result["h2_harm"]) == {"local"}
    met = jf.judge_d13(_d12_run(_stats(24, 6, 0.001), _stats(20, 10, 0.099)))
    assert met["family"]["H1-local-D13"]["met"] is True and met["h1_met"] is True


def test_no_d13_run_no_d13_verdict(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(jf, "D13_LOCAL", tmp_path / "missing.json")
    monkeypatch.setattr(jf, "D13_RESULT", tmp_path / "result.json")
    assert jf.main(["--family", "d13", "--write"]) == 1
    assert not (tmp_path / "result.json").exists()
    assert "nothing written" in capsys.readouterr().out
