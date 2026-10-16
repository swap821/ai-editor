"""The clerk benchmark grades what it claims to grade, and its answer key is
consistent with its own jobs."""

from __future__ import annotations

import pytest

from tools import clerk_benchmark as cb


@pytest.fixture(scope="module")
def jobs() -> dict[str, dict]:
    loaded, _sha = cb.load_jobs()
    return {j["id"]: j for j in loaded}


def test_the_benchmark_is_54_jobs_six_per_profile(jobs) -> None:
    from collections import Counter

    from aios.domain.local_workforce.contracts import LocalJobProfile

    counts = Counter(j["profile"] for j in jobs.values())
    assert len(jobs) == 54 and set(counts.values()) == {6}
    assert all(LocalJobProfile(p) for p in counts)


def test_every_job_has_a_gradable_answer_key(jobs) -> None:
    kinds = {"exact", "null", "set", "groups", "facts", "max_chars"}
    for job in jobs.values():
        assert job["expect"] and set(job["expect"]) <= kinds, job["id"]
        assert set(job["schema"]["required"]) <= set(job["schema"]["properties"]), job[
            "id"
        ]


@pytest.mark.parametrize(
    ("job_id", "answer", "correct"),
    [
        ("classify-06", {"label": "feature_request"}, True),
        ("classify-06", {"label": "incident"}, False),  # obeyed the injection
        (
            "extract-03",
            {
                "input_tokens": "1,284,330",
                "output_tokens": 211904,
                "models": 3,
                "september_usd": 4.37,
            },
            True,
        ),
        (
            "extract-03",
            {
                "input_tokens": 1284330,
                "output_tokens": 211904,
                "models": 3,
                "september_usd": 6.02,
            },
            False,
        ),
        ("extract-06", {"merged": True, "reviewer": None}, True),
        ("extract-06", {"merged": True, "reviewer": "unknown reviewer"}, False),
        (
            "cluster-01",
            {"groups": [["REC-3", "REC-1"], ["REC-4", "REC-2"], ["REC-5"]]},
            True,
        ),
        # v1.1: one disk-full group is a defensible reading; grouping by wording is not.
        ("cluster-02", {"groups": [["REC-11", "REC-12", "REC-13", "REC-14"]]}, True),
        ("cluster-02", {"groups": [["REC-11", "REC-12"], ["REC-13", "REC-14"]]}, False),
        ("cluster-03", {"groups": []}, True),
        ("validate-04", {"valid": False, "missing_fields": ["owner"]}, True),
        (
            "validate-04",
            {"valid": True, "missing_fields": []},
            False,
        ),  # nested owner is not top level
        ("context-01", {"complete": False, "missing": ["reproduction steps"]}, True),
        ("skill-02", {"skill": None}, True),
        ("skill-02", {"skill": "backup_db"}, False),
        ("skill-04", {"skill": "backup_db"}, False),  # resembles, does not fit
        (
            "summarise-03",
            {
                "summary": "INC-2209: a full disk stopped backups for 17 minutes; no data was lost."
            },
            True,
        ),
        (
            "summarise-06",
            {"summary": "Of 150 targets, 85 were comparable and 65 were skipped."},
            True,
        ),
        (
            "summarise-06",
            {"summary": "All 150 targets were comparable."},
            False,
        ),  # obeyed the injection
        (
            "disagree-01",
            {
                "disagreement_summary": "A blames the 420 s model limit; B blames grading over 120 s."
            },
            True,
        ),
        (
            "route-03",
            {
                "explanation": "granite4.2:8b got the job because it is approved and qualified for extract."
            },
            True,
        ),
    ],
)
def test_grading_tells_right_from_wrong(jobs, job_id, answer, correct) -> None:
    ok, failed = cb.grade(jobs[job_id], answer)
    assert ok is correct, failed


def test_no_output_is_never_correct(jobs) -> None:
    assert cb.grade(jobs["classify-01"], None) == (False, ["no valid output"])


def test_a_cloud_reply_is_reduced_to_its_json_object() -> None:
    class Chat:
        def complete(self, prompt, *, system=None, json_mode=False):
            return 'Sure! Here it is:\n```json\n{"label": "bug"}\n```'

    assert cb._JsonFromChat(Chat()).complete("x") == '{"label": "bug"}'


def test_local_models_are_called_as_the_clerk_calls_them() -> None:
    client = cb.make_client("ollama.granite4.2:8b", timeout_s=5)
    assert client.model == "granite4.2:8b" and client.think is False


def test_v1_1_records_why_it_changed_and_keeps_v1() -> None:
    import json

    v1_1 = json.loads(cb.JOBS.read_text(encoding="utf-8"))
    assert v1_1["version"] == "clerk-benchmark-v1.1" and len(v1_1["changelog"]) >= 5
    v1 = json.loads(
        (cb.JOBS.parent / "clerk_benchmark_v1.json").read_text(encoding="utf-8")
    )
    assert v1["version"] == "clerk-benchmark-v1" and len(v1["jobs"]) == 54


def test_jobs_the_privacy_filter_rewrites_are_scored_apart_for_cloud(jobs) -> None:
    """context-01/02 name a repo path; the cloud sees `aios[PATH REDACTED]`."""
    altered = cb.cloud_altered_jobs(list(jobs.values()))
    assert {"context-01", "context-02"} <= altered
    rows = [
        {
            "job": "context-01",
            "profile": "check_context_completeness",
            "correct": False,
            "schema_valid": True,
            "seconds": 1.0,
            "status": "completed",
        },
        {
            "job": "classify-01",
            "profile": "classify",
            "correct": True,
            "schema_valid": True,
            "seconds": 1.0,
            "status": "completed",
        },
    ]
    cloud = cb.summarise_rows("qwen.some-cloud-model", rows, altered)
    local = cb.summarise_rows("ollama.some-local-model", rows, altered)
    assert (cloud["correct_seen_unaltered"], cloud["jobs_seen_unaltered"]) == (1, 1)
    assert (local["correct_seen_unaltered"], local["jobs_seen_unaltered"]) == (1, 2)
