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
