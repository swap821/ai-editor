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

D12 (PAYOFF_PREREGISTRATION.md D12) is its own family: Holm over
{H1-cloud-D12, H1c-cloud-D12, H1-local-D12, H1c-local-D12}; H2 per cohort. It
is judged only when BOTH trails exist -- a partial family is never written as a
verdict -- and its result sits beside Phase 8's, which the usefulness gate
then stops reading (written 2026-10-21, before the local run produced data):

    python tools/judge_payoff_family.py --family d12 [--write]
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
D12_CLOUD = LEARNING / "payoff_d12_cloud_trail.json"
D12_LOCAL = LEARNING / "payoff_d12_local_trail.json"
D12_RESULT = LEARNING / "payoff_d12_judged_result.json"
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


def family_verdict(members: dict[str, dict]) -> dict[str, dict]:
    """D4, the one rule for every family: Holm over the members' own p-values;
    a member is met only if its direction is positive AND its Holm p < ALPHA."""
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
    return family


def harm(cohorts: dict[str, dict]) -> dict[str, dict]:
    """H2 per cohort, uncorrected: ON worse than OFF over all comparable pairs."""
    return {
        cohort: {
            "pairs": s["pairs"],
            "on_only": s["on_only"],
            "off_only": s["off_only"],
            "p_value": s["p_value"],
            "violated": s["off_only"] > s["on_only"] and s["p_value"] < ALPHA,
        }
        for cohort, s in cohorts.items()
    }


def judge(cloud: dict, local: dict, cloud_base: dict, local_base: dict) -> dict:
    cs, ls = cloud["summary"], local["summary"]
    family = family_verdict(
        {
            "H1-cloud": cs["novel"],
            "H1c-cloud": cs["content_novel"],
            "H1-7B": ls["novel"],
        }
    )
    h2 = harm({"cloud": cs["all"], "7B": ls["all"]})
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


_D12_KEYS = ("run_id", "corpus_sha", "harness_sha", "models", "samples", "placebo")


def judge_d12(cloud: dict, local: dict) -> dict:
    """The D12 family (PAYOFF_PREREGISTRATION.md D12). No H3: D12 registers none."""
    cs, ls = cloud["summary"], local["summary"]
    family = family_verdict(
        {
            "H1-cloud-D12": cs["novel"],
            "H1c-cloud-D12": cs["content_novel"],
            "H1-local-D12": ls["novel"],
            "H1c-local-D12": ls["content_novel"],
        }
    )
    h2 = harm({"cloud": cs["all"], "local": ls["all"]})
    met = any(m["met"] for m in family.values())
    parts = ", ".join(
        f"{n} {m['on_only']} vs {m['off_only']} (Holm p={m['holm_p']:.2f})"
        for n, m in family.items()
    )
    summary = (
        f"D12 family {'MET' if met else 'not met'}: {parts}; "
        f"harm (H2) {'seen' if any(v['violated'] for v in h2.values()) else 'not seen'}"
    )
    return {
        "judged": "D12 family, docs/learning/PAYOFF_PREREGISTRATION.md D12",
        "result_doc": "docs/learning/PAYOFF_D12_RESULT.md",
        "runs": {
            "cloud": {k: cloud.get(k) for k in _D12_KEYS},
            "local": {k: local.get(k) for k in _D12_KEYS},
        },
        "family_alpha": ALPHA,
        "family": family,
        "h2_harm": h2,
        "h1_met": met,
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the result file")
    parser.add_argument("--family", choices=("phase8", "d12"), default="phase8")
    args = parser.parse_args(argv)
    if args.family == "d12":
        missing = [p.name for p in (D12_CLOUD, D12_LOCAL) if not p.is_file()]
        if missing:
            print(
                f"D12 family incomplete: {', '.join(missing)} missing. "
                "A partial family is not a verdict; nothing written."
            )
            return 1
        result, target = judge_d12(_load(D12_CLOUD), _load(D12_LOCAL)), D12_RESULT
    else:
        result = judge(
            _load(CLOUD), _load(LOCAL), _load(CLOUD_BASELINE), _load(LOCAL_BASELINE)
        )
        target = RESULT
    text = json.dumps(result, indent=2) + "\n"
    if args.write:
        with target.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"wrote {target.relative_to(REPO).as_posix()}")
    print(result["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
