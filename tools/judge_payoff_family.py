"""Judge the registered Phase 8 family from the two runs' committed trails.

PAYOFF_PREREGISTRATION.md D4/D5: Holm over {H1-cloud, H1c-cloud, H1-7B}; a member
is met only if its direction is positive AND its Holm-adjusted p < 0.05. H2
(harm) per cohort, uncorrected. H3 (hardening preserves utility) per cohort: the
ON arm's earned samples per target against that cohort's baseline, on targets
whose ON arm reached the model in both runs (McNemar at K = 1, sign-flip at K > 1).

Every statistic comes from tools/learning_payoff.py (holm_adjust, mcnemar_exact,
sign_flip_exact); each member's p is the harness's own, read from its trail.

    python tools/judge_payoff_family.py            # prints the verdict
    python tools/judge_payoff_family.py --write    # writes docs/learning/payoff_judged_result.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools import learning_payoff as lp  # noqa: E402

LEARNING = REPO / "docs" / "learning"
CLOUD = LEARNING / "payoff_phase8_cloud_trail.json"
LOCAL = LEARNING / "payoff_phase8_7b_trail.json"
CLOUD_BASELINE = LEARNING / "payoff_cloud_baseline_trail.json"
LOCAL_BASELINE = LEARNING / "payoff_phase0_baseline_trail.json"
RESULT = LEARNING / "payoff_judged_result.json"
ALPHA = 0.05


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def on_earned(pair: dict) -> int | None:
    """Earned ON samples for one target, or None if ON never reached the model."""
    samples = (pair.get("samples") or {}).get("on")
    if isinstance(samples, list) and samples:
        if not all(s.get("reached_model") for s in samples):
            return None
        return sum(1 for s in samples if s.get("earned"))
    on = pair.get("on")
    if not isinstance(on, dict) or not on.get("reached_model"):
        return None
    return 1 if on.get("earned") else 0


def h3(run: dict, baseline: dict) -> dict:
    now = {p["target"]: on_earned(p) for p in run["pairs"]}
    before = {p["target"]: on_earned(p) for p in baseline["pairs"]}
    both = [t for t in now if now[t] is not None and before.get(t) is not None]
    diffs = [now[t] - before[t] for t in both]
    gains = sum(1 for d in diffs if d > 0)
    drops = sum(1 for d in diffs if d < 0)
    k = int(run.get("samples") or 1)
    p = lp.mcnemar_exact(gains, drops) if k == 1 else lp.sign_flip_exact(diffs)
    return {
        "targets_reached_in_both": len(both),
        "phase8_better": gains,
        "baseline_better": drops,
        "p_value": p,
        "violated": drops > gains and p < ALPHA,
    }


def judge(cloud: dict, local: dict, cloud_base: dict, local_base: dict) -> dict:
    cs, ls = cloud["summary"], local["summary"]
    members = {
        "H1-cloud": cs["novel"],
        "H1c-cloud": cs["content_novel"],
        "H1-7B": ls["novel"],
    }
    adjusted = lp.holm_adjust({n: float(s["p_value"]) for n, s in members.items()})
    family = {}
    for name, s in members.items():
        positive = s["on_only"] > s["off_only"]
        family[name] = {
            "arms": s["arms"],
            "pairs": s["pairs"],
            "samples": s["samples"],
            "on_earned": s["on_earned"],
            "off_earned": s["off_earned"],
            "on_only": s["on_only"],
            "off_only": s["off_only"],
            "direction": "positive" if positive else "negative or zero",
            "raw_p": float(s["p_value"]),
            "holm_p": adjusted[name],
            "met": positive and adjusted[name] < ALPHA,
        }
    h2 = {
        cohort: {
            "pairs": s["pairs"],
            "on_only": s["on_only"],
            "off_only": s["off_only"],
            "p_value": s["p_value"],
            "violated": s["off_only"] > s["on_only"] and s["p_value"] < ALPHA,
        }
        for cohort, s in (("cloud", cs["all"]), ("7B", ls["all"]))
    }
    h3s = {"cloud": h3(cloud, cloud_base), "7B": h3(local, local_base)}
    met = any(m["met"] for m in family.values())
    parts = ", ".join(
        f"{n} {m['on_only']} vs {m['off_only']} (Holm p={m['holm_p']:.2f})"
        for n, m in family.items()
    )
    summary = (
        f"Phase 8 family {'MET' if met else 'not met'}: {parts}; "
        f"harm (H2) {'seen' if any(v['violated'] for v in h2.values()) else 'not seen'}; "
        "hardening kept utility (H3) "
        f"{'no' if any(v['violated'] for v in h3s.values()) else 'yes'}"
    )
    keys = ("run_id", "corpus_sha", "harness_sha", "models", "samples", "placebo")
    return {
        "judged": "Phase 8 family, docs/learning/PAYOFF_PREREGISTRATION.md D4/D5",
        "result_doc": "docs/learning/PAYOFF_PHASE8_RESULT.md",
        "runs": {
            "cloud": {k: cloud[k] for k in keys},
            "7B": {k: local[k] for k in keys},
        },
        "family_alpha": ALPHA,
        "family": family,
        "h2_harm": h2,
        "h3_hardening_preserves_utility": h3s,
        "h1_met": met,
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help=f"write {RESULT.name}")
    args = parser.parse_args(argv)
    result = judge(
        _load(CLOUD), _load(LOCAL), _load(CLOUD_BASELINE), _load(LOCAL_BASELINE)
    )
    text = json.dumps(result, indent=2) + "\n"
    if args.write:
        with RESULT.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"wrote {RESULT.relative_to(REPO).as_posix()}")
    print(result["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
