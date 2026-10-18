"""D12: a strong model TEACHES -- it writes every lesson -- while the student
attempts; and practice workers can run in parallel without sharing a corpus
worktree, a store or a trail.

Practice run 2 (2026-10-12) had the student write its own lessons: 4 of 19
were false. The lesson writer is the lever, so it is a parameter now.
"""

from __future__ import annotations

import json

import pytest

from tools import organic_chain_run as ocr


def _ladder():
    return [("student", object()), ("teacher", object())]


def test_without_a_teacher_the_first_model_writes_the_lessons() -> None:
    ladder = _ladder()
    assert ocr.choose_teacher(ladder, None, timeout_s=1) is ladder[0]


def test_a_teacher_in_the_ladder_is_reused_not_resolved_again() -> None:
    ladder = _ladder()

    def resolve(spec, timeout_s):
        raise AssertionError("a teacher already in the ladder must not be resolved")

    assert ocr.choose_teacher(ladder, "teacher", timeout_s=1, resolve=resolve) == (
        "teacher",
        ladder[1][1],
    )


def test_a_teacher_outside_the_ladder_is_resolved() -> None:
    teacher_client = object()
    asked: list[str] = []

    def resolve(spec, timeout_s):
        asked.append(spec)
        return teacher_client, spec

    assert ocr.choose_teacher(_ladder(), "elsewhere", timeout_s=1, resolve=resolve) == (
        "elsewhere",
        teacher_client,
    )
    assert asked == ["elsewhere"]


def test_an_unreachable_teacher_refuses_the_run_instead_of_standing_in() -> None:
    """A stand-in would write lessons attributed to a model that never wrote them."""

    def resolve(spec, timeout_s):
        raise ocr.CorpusError("not configured")

    with pytest.raises(ocr.CorpusError):
        ocr.choose_teacher(_ladder(), "elsewhere", timeout_s=1, resolve=resolve)


def test_each_worker_gets_its_own_store_corpus_and_trail(tmp_path, monkeypatch) -> None:
    # Restored at teardown: main() rebinds the module paths.
    monkeypatch.setattr(ocr, "DB", ocr.DB)
    monkeypatch.setattr(ocr, "WORKTREE", ocr.WORKTREE)
    monkeypatch.setattr(ocr, "TRAIL", ocr.TRAIL)
    seen: dict = {}

    def run_chain(**kwargs):
        seen.update(kwargs, db=ocr.DB, worktree=ocr.WORKTREE)
        raise ocr.CorpusError("stop before any model or corpus")

    monkeypatch.setattr(ocr, "run_chain", run_chain)
    store, corpus, trail = (
        tmp_path / "w1.db",
        tmp_path / "corpus-w1",
        tmp_path / "w1.jsonl",
    )
    assert (
        ocr.main(
            [
                "--models",
                "student,teacher",
                "--teacher",
                "teacher",
                "--db",
                str(store),
                "--corpus-dir",
                str(corpus),
                "--trail",
                str(trail),
            ]
        )
        == 1
    )
    assert seen["teacher"] == "teacher"
    assert seen["db"] == store.resolve()
    assert seen["worktree"] == corpus.resolve()
    rows = [json.loads(line) for line in trail.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["outcome"] == "aborted"


# --- D12's critic ---------------------------------------------------------


class _Critic:
    def __init__(self, reply: str = "", *, raises: Exception | None = None) -> None:
        self.reply = reply
        self.raises = raises
        self.prompts: list[str] = []

    def complete(self, prompt, *, system=None, json_mode=False):
        self.prompts.append(prompt)
        if self.raises is not None:
            raise self.raises
        return self.reply


@pytest.mark.parametrize(
    ("reply", "verdict"),
    [
        ('{"verdict": "true", "reason": "the code returns frozenset()"}', "true"),
        ('{"verdict": "FALSE", "reason": "it never raises"}', "false"),
        ('Here is my answer:\n{"verdict": "true", "reason": "ok"}\nThanks', "true"),
        ('{"verdict": "probably", "reason": "?"}', "unsure"),
        ("I think it is right.", "unsure"),
        ("", "unsure"),
    ],
)
def test_the_critic_keeps_a_lesson_only_on_a_readable_true(reply, verdict) -> None:
    got, _reason = ocr.critique_lesson(
        _Critic(reply),
        lesson_text="approved_organ_ids returns an empty frozenset",
        root_cause="the test expected an exception",
        function="approved_organ_ids",
        source="def approved_organ_ids(x):\n    return frozenset()\n",
        change="-    with pytest.raises(...)\n+    assert f(x) == frozenset()\n",
    )
    assert got == verdict


def test_an_unavailable_critic_keeps_nothing() -> None:
    verdict, reason = ocr.critique_lesson(
        _Critic(raises=TimeoutError("slow")),
        lesson_text="l",
        root_cause="r",
        function="f",
        source="s",
        change="c",
    )
    assert verdict == "unsure"
    assert "TimeoutError" in reason


def test_the_critic_sees_the_module_source_and_the_change() -> None:
    critic = _Critic('{"verdict": "true", "reason": "ok"}')
    ocr.critique_lesson(
        critic,
        lesson_text="L",
        root_cause="R",
        function="target_fn",
        source="def target_fn(a):\n    return a\n",
        change="+assert target_fn(1) == 1",
    )
    assert "def target_fn(a)" in critic.prompts[0]
    assert "+assert target_fn(1) == 1" in critic.prompts[0]


@pytest.mark.parametrize(
    ("reply", "kept"), [('{"verdict": "true"}', True), ('{"verdict": "false"}', False)]
)
def test_a_rejected_lesson_leaves_recall_in_the_practice_store(
    tmp_path, reply, kept
) -> None:
    from types import SimpleNamespace

    from aios.memory.db import init_memory_db
    from aios.memory.mistake import MistakeMemory

    db = tmp_path / "practice.db"
    init_memory_db(db)
    mistakes = MistakeMemory(db_path=db)
    lesson = mistakes.record(
        "run:target#resolved",
        "AssertionError",
        "approved_organ_ids returns an empty frozenset for no approvals",
        "assert the empty frozenset",
        "approved_organ_ids returns an empty frozenset when nothing is approved",
        -0.1,
    )
    mistakes.promote(lesson)
    module = tmp_path / "corpus" / "aios" / "m.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "def approved_organ_ids(x):\n    return frozenset()\n", encoding="utf-8"
    )
    log: list = []

    result = ocr._apply_critic(
        _Critic(reply),
        mistakes,
        lesson,
        target=SimpleNamespace(
            module="aios/m.py",
            function="approved_organ_ids",
            label="aios/m.py::approved_organ_ids",
            source="",
        ),
        corpus_root=tmp_path / "corpus",
        change="+assert approved_organ_ids(1) == frozenset()",
        log=log,
    )

    status = mistakes.get(lesson)["verification_status"]
    recalled = [
        r["mistake_id"]
        for r in mistakes.relevant_verified("approved_organ_ids frozenset approvals")
    ]
    assert log[0]["verdict"] == ("true" if kept else "false")
    if kept:
        assert result == lesson and status == "verified" and lesson in recalled
    else:
        assert (
            result is None
            and status == ocr.REJECTED_BY_CRITIC
            and lesson not in recalled
        )


def test_a_critic_that_is_the_teacher_refuses_the_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ocr, "DB", tmp_path / "practice.db")
    monkeypatch.setattr(ocr, "resolve_client", lambda spec, timeout_s: (object(), spec))
    with pytest.raises(ocr.CorpusError, match="second opinion"):
        ocr.run_chain(
            models="student,teacher",
            targets=1,
            retries=0,
            model_timeout=1,
            teacher="teacher",
            critic="teacher",
        )


# --- D12: a throttled teacher is retried, not graded --------------------------


def test_a_throttled_reflection_is_retried_then_succeeds() -> None:
    calls, waits = [], []

    def call():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("ThrottlingException: Too many requests")
        return "lesson"

    assert ocr.retry_transient(call, waits=(1, 2, 3), sleep=waits.append) == "lesson"
    assert waits == [1, 2] and len(calls) == 3


def test_a_non_transient_error_is_raised_at_once() -> None:
    waits = []
    with pytest.raises(ValueError):
        ocr.retry_transient(
            lambda: (_ for _ in ()).throw(ValueError("bad")),
            waits=(1,),
            sleep=waits.append,
        )
    assert waits == []


def test_throttling_that_never_ends_still_fails_after_the_waits() -> None:
    waits = []

    def call():
        raise RuntimeError("ThrottlingException")

    with pytest.raises(RuntimeError):
        ocr.retry_transient(call, waits=(1, 2), sleep=waits.append)
    assert waits == [1, 2]


def test_a_throttled_attempt_is_rerun_not_graded(monkeypatch) -> None:
    from types import SimpleNamespace

    outcomes = iter(
        [
            SimpleNamespace(
                outcome="model_error", notes=["ThrottlingException: Too many requests"]
            ),
            SimpleNamespace(outcome="rejected", notes=["assert 4 == 5"]),
        ]
    )
    monkeypatch.setattr(ocr, "_attempt_one", lambda *a, **k: next(outcomes))
    waits = []
    record = ocr.attempt_with_retry(
        "corpus", "client", "target", waits=(7,), sleep=waits.append
    )
    assert record.outcome == "rejected" and waits == [7]


def test_a_real_model_error_is_not_retried(monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        ocr,
        "_attempt_one",
        lambda *a, **k: SimpleNamespace(
            outcome="model_error", notes=["401 Unauthorized"]
        ),
    )
    waits = []
    assert (
        ocr.attempt_with_retry("c", "c", "t", waits=(7,), sleep=waits.append).outcome
        == "model_error"
    )
    assert waits == []


def _attempt(reached: bool, note: str = "") -> object:
    from types import SimpleNamespace

    return SimpleNamespace(reached_model=reached, notes=[note] if note else [])


def test_a_target_some_model_reached_resets_the_unreached_streak() -> None:
    assert ocr.count_unreached(2, [_attempt(False, "x"), _attempt(True)]) == 0
    assert ocr.count_unreached(2, []) == 0


def test_a_blocked_provider_stops_the_run_after_three_unreached_targets() -> None:
    """2026-10-18: Bedrock refused every inference ("Operation not allowed") and
    the practice raced on -- 819 refusals in two minutes -- filing targets no
    model ever saw. Three unreached targets in a row stop it, naming why."""
    refused = "ValidationException: Operation not allowed"
    streak = 0
    for _ in range(ocr.UNREACHED_TARGETS_BEFORE_STOP - 1):
        streak = ocr.count_unreached(streak, [_attempt(False, refused)] * 3)
    assert streak == ocr.UNREACHED_TARGETS_BEFORE_STOP - 1
    with pytest.raises(ocr.ProviderUnavailable, match="Operation not allowed"):
        ocr.count_unreached(streak, [_attempt(False, refused)] * 3)


def test_the_stop_is_recorded_like_any_other_abort() -> None:
    # main() records every CorpusError as an aborted run in the trail.
    assert issubclass(ocr.ProviderUnavailable, ocr.CorpusError)
