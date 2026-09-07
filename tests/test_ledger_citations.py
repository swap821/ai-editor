"""A ledger verdict may not contradict the record it cites.

WHY THIS EXISTS. On 2026-09-07 a draft of organ 55's C10 claimed the
nine-mission bar reached 9/9 CONFORMANT. That record says 8/9 and NOT
CONFORMANT in every cohort -- the 9/9 runs are the later set, after M1 was made
scorable. It was caught by opening the file before asserting.

That is vigilance, not a control, and this project's whole standard is that
vigilance does not count. The rules beside this one check the ledger against its
OWN fields; neither could see a claim about a cited FILE, which is where the
near-miss landed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_spec = importlib.util.spec_from_file_location(
    "_verify_citations", REPO_ROOT / "scripts" / "verify_organ_twelve_conditions.py"
)
_verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verify)

#: The record that caused the near-miss: it holds 8/9 and nothing higher.
_EIGHT_OF_NINE = "release/organ-55/2026-09-07-three-cohort-bar-nine-missions.md"


def _record(**verdicts):
    return SimpleNamespace(organ_id=55, name="probe", condition_verdicts=verdicts)


def test_the_draft_i_nearly_committed_is_refused() -> None:
    """THE BAR, reproduced rather than asserted.

    This is the shape of the text that was almost written into the ledger: a
    9/9 claim citing a record that contains only 8/9.
    """
    failures = _verify._citation_failures(
        _record(
            C10=(
                "the NINE-mission set reached 9/9 CONFORMANT in three of four "
                f"runs on 2026-09-07 ({_EIGHT_OF_NINE})."
            )
        ),
        REPO_ROOT,
    )

    assert failures, "the draft that claimed 9/9 against an 8/9 record passed"
    assert "9/9" in failures[0][1]


def test_a_claim_the_cited_record_supports_passes() -> None:
    """A rule that fires on the truth is worse than no rule.

    The same record, quoted accurately, must not be flagged.
    """
    assert not _verify._citation_failures(
        _record(C10=f"three consecutive cohorts at 8/9 ({_EIGHT_OF_NINE})."),
        REPO_ROOT,
    )


def test_a_citation_that_does_not_exist_is_refused() -> None:
    """A record renamed or deleted leaves its claim unfalsifiable.

    The score check alone would skip it in silence -- there would be nothing to
    compare against -- so absence has to be its own failure.
    """
    failures = _verify._citation_failures(
        _record(
            C10="see release/organ-55/2026-01-01-not-a-real-file.md for the 5/5 run."
        ),
        REPO_ROOT,
    )

    assert failures
    assert "does not exist" in failures[0][1]


def test_a_verdict_citing_nothing_is_untouched() -> None:
    """Scoped deliberately.

    Most verdicts cite no record and legitimately contain numbers. Flagging
    those would make the rule cry wolf in the artifact readers trust first,
    which is worse than having no rule.
    """
    assert not _verify._citation_failures(
        _record(
            C1="MET - 3/3 production entrypoints resolve",
            C2="MET - the suite ran 12/12",
        ),
        REPO_ROOT,
    )


def test_one_supporting_record_among_several_is_enough() -> None:
    """A verdict may cite several records and draw one number from each.

    Requiring every score in every cited file would fail correct history.
    """
    assert not _verify._citation_failures(
        _record(
            C10=(
                "9/9 after the M1 fix "
                "(release/organ-55/2026-09-07-m1-can-score.md), and 8/9 before "
                f"it ({_EIGHT_OF_NINE})."
            )
        ),
        REPO_ROOT,
    )


def test_the_shipped_ledger_has_no_uncited_score() -> None:
    """The repository as shipped must satisfy the rule.

    On its first run this failed: C10 claimed `>=4/5` on gemini-3.7-flash and
    cited no record for it -- three files cited, four scores claimed. The record
    existed; the verdict simply never pointed at it. Fixed by adding the
    citation, not by loosening the rule, because an uncited number is exactly
    the unverifiable prose claim this project refuses.
    """
    from aios.application.governance.organ_ledger import load_ledger

    offenders = [
        (r.organ_id, cond, why)
        for r in load_ledger(REPO_ROOT / ".aios/state/ORGAN_GREEN_LEDGER.json")
        for cond, why in _verify._citation_failures(r, REPO_ROOT)
    ]

    assert not offenders, f"ledger makes claims its records do not support: {offenders}"
