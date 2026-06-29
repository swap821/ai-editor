"""CRAG Slice 1 — decompose-then-recompose context refinement.

The single biggest accuracy driver in the CRAG ablation (-5.1% when removed):
shatter retrieved context into sentence strips, drop the noise (sub-min_chars
fragments + strips with no query relevance), recompose only the golden strips.
Pure + deterministic by default (uses aios.memory.relevance); an optional `keep`
callback can override the filter. See
docs/superpowers/specs/2026-06-29-crag-for-gagos-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass

from aios.memory.crag import (
    CalibrationResult,
    CragAction,
    RetrievalVerdict,
    calibrate_thresholds,
    evaluate_retrieval,
    external_retrieve,
    refine_context,
)


@dataclass(frozen=True)
class _Hit:
    """Minimal stand-in for RetrievalResult (evaluate_retrieval duck-types it)."""

    text: str
    faiss: float = 0.0
    verification_status: str = "unverified"


def test_refine_keeps_golden_sentence_and_drops_filler() -> None:
    query = "capital of France"
    doc = (
        "This document was written long ago by many authors. "
        "The capital of France is Paris, a major European city. "
        "We hope you enjoyed reading this introductory paragraph."
    )
    refined = refine_context(query, [doc])
    assert "Paris" in refined  # the golden strip survived
    assert "capital of France" in refined
    assert "enjoyed reading" not in refined  # pure filler dropped
    assert len(refined) < len(doc)  # denser than the original


def test_refine_drops_short_fragments() -> None:
    query = "alpha beta"
    doc = "OK. The alpha and beta parameters control the model behavior precisely."
    refined = refine_context(query, [doc])
    assert "OK." not in refined  # sub-20-char fragment dropped
    assert "alpha" in refined and "beta" in refined


def test_refine_recompose_preserves_order() -> None:
    query = "sky ocean"
    doc = "The sky is blue and vast above us. The ocean is deep and wide below us."
    refined = refine_context(query, [doc])
    assert refined.index("sky") < refined.index("ocean")


def test_refine_empty_input_is_empty() -> None:
    assert refine_context("q", []) == ""
    assert refine_context("q", ["   ", ""]) == ""
    assert refine_context("q", ["short"]) == ""  # all fragments below min_chars


def test_refine_never_blanks_when_no_lexical_overlap() -> None:
    # A long sentence with zero query-term overlap still yields its best strip,
    # never an empty block — the never-blank contract for the default path.
    query = "quantum entanglement"
    doc = "The garden was full of blooming roses and tall green trees in summer."
    refined = refine_context(query, [doc])
    assert refined != ""
    assert "garden" in refined


def test_refine_custom_keep_callback_controls_filtering() -> None:
    query = "anything"
    doc = "First candidate sentence here now. Second candidate sentence here now."
    refined = refine_context(query, [doc], keep=lambda _q, s: "Second" in s)
    assert "Second" in refined
    assert "First" not in refined


def test_refine_keep_callback_error_keeps_strip() -> None:
    # A model-backed strip filter that throws must NOT drop real context (fail-open
    # at the strip level — recall is an enhancement, never a gate).
    def boom(_q: str, _s: str) -> bool:
        raise RuntimeError("strip judge unreachable")

    doc = "This is a sufficiently long sentence to survive decomposition cleanly."
    refined = refine_context("q", [doc], keep=boom)
    assert "sufficiently long sentence" in refined


def test_refine_spans_multiple_documents_in_order() -> None:
    query = "tea coffee"
    refined = refine_context(
        query,
        [
            "The morning tea was warm and comforting on a cold day.",
            "Some unrelated filler about distant mountains and rivers.",
            "The afternoon coffee was strong and bitter as usual today.",
        ],
    )
    assert "tea" in refined and "coffee" in refined
    assert "mountains" not in refined  # the irrelevant middle document dropped
    assert refined.index("tea") < refined.index("coffee")


# ── Slice 2: evaluate_retrieval + tripartite gate ───────────────────────────

def test_evaluate_correct_when_a_hit_exceeds_upper() -> None:
    hits = [_Hit("irrelevant note", faiss=0.1), _Hit("strong semantic hit", faiss=0.9)]
    verdict = evaluate_retrieval("q", hits, upper=0.6, lower=0.2)
    assert verdict.action is CragAction.CORRECT
    assert verdict.score == 0.9


def test_evaluate_incorrect_when_all_below_lower() -> None:
    # Low semantic AND no lexical overlap with the query → junk retrieval.
    hits = [_Hit("apples and oranges", faiss=0.05), _Hit("bananas too", faiss=0.1)]
    verdict = evaluate_retrieval("quantum physics", hits, upper=0.6, lower=0.2)
    assert verdict.action is CragAction.INCORRECT


def test_evaluate_ambiguous_between_thresholds() -> None:
    hits = [_Hit("a partially related thing", faiss=0.4)]
    verdict = evaluate_retrieval("q", hits, upper=0.6, lower=0.2)
    assert verdict.action is CragAction.AMBIGUOUS


def test_evaluate_score_uses_max_of_faiss_and_lexical() -> None:
    # Low semantic score, but strong lexical overlap with the query → high confidence.
    hits = [_Hit("the alpha beta gamma parameters", faiss=0.05)]
    verdict = evaluate_retrieval("alpha beta gamma", hits, upper=0.6, lower=0.2)
    assert verdict.score > 0.6  # lexical rescued it
    assert verdict.action is CragAction.CORRECT


def test_evaluate_empty_hits_is_incorrect() -> None:
    verdict = evaluate_retrieval("q", [], upper=0.6, lower=0.2)
    assert verdict.action is CragAction.INCORRECT
    assert verdict.score == 0.0


def test_evaluate_judge_can_only_lower_not_raise() -> None:
    # Caution-only clamp: a generous judge cannot upgrade a junk hit.
    hits = [_Hit("totally unrelated text here", faiss=0.05)]
    verdict = evaluate_retrieval(
        "quantum physics", hits, upper=0.6, lower=0.2, judge=lambda _q, _s: 1.0
    )
    assert verdict.action is CragAction.INCORRECT  # judge's 1.0 ignored upward

    # ...but a strict judge CAN add caution (lower a strong deterministic score).
    strong = [_Hit("strong hit", faiss=0.95)]
    lowered = evaluate_retrieval(
        "q", strong, upper=0.6, lower=0.2, judge=lambda _q, _s: 0.1
    )
    assert lowered.score == 0.1
    assert lowered.action is CragAction.INCORRECT


def test_evaluate_judge_error_falls_back_to_deterministic() -> None:
    def boom(_q: str, _s: str) -> float:
        raise RuntimeError("judge down")

    hits = [_Hit("strong hit", faiss=0.9)]
    verdict = evaluate_retrieval("q", hits, upper=0.6, lower=0.2, judge=boom)
    assert verdict.action is CragAction.CORRECT  # deterministic stands
    assert verdict.score == 0.9


def test_retrieval_verdict_exposes_per_hit_scores() -> None:
    hits = [_Hit("x", faiss=0.9), _Hit("y", faiss=0.3)]
    verdict = evaluate_retrieval("q", hits, upper=0.6, lower=0.2)
    assert isinstance(verdict, RetrievalVerdict)
    assert verdict.per_hit == [0.9, 0.3]


# ── Slice 2: wiring into _recall_memory (opt-in, AIOS_CRAG) ──────────────────

def _patch_recall(monkeypatch, hits, *, crag: bool):
    from aios import config
    from aios.api import main

    monkeypatch.setattr(main, "hybrid_search", lambda _q, top_k=3: hits)
    monkeypatch.setattr(config, "CRAG", crag)
    monkeypatch.setattr(config, "CRAG_UPPER", 0.6)
    monkeypatch.setattr(config, "CRAG_LOWER", 0.2)
    return main


def test_recall_memory_crag_off_is_legacy_bullets(monkeypatch) -> None:
    hits = [_Hit("the alpha beta result is here and relevant", faiss=0.9, verification_status="verified")]
    main = _patch_recall(monkeypatch, hits, crag=False)
    out = main._recall_memory("alpha beta")
    assert out is not None
    assert "- the alpha beta result is here and relevant" in out  # unrefined bullet form


def test_recall_memory_crag_drops_incorrect_retrieval(monkeypatch) -> None:
    # Low semantic + zero lexical overlap → INCORRECT → the junk recall is excluded
    # from the prompt entirely (the core anti-hallucination win of Slice 2).
    hits = [_Hit("completely unrelated banana content here", faiss=0.05)]
    main = _patch_recall(monkeypatch, hits, crag=True)
    assert main._recall_memory("quantum physics") is None


def test_recall_memory_crag_refines_and_preserves_trust(monkeypatch) -> None:
    hits = [
        _Hit(
            "Intro filler with no real content at all here. "
            "The capital of France is Paris indeed. "
            "Some closing remarks that are pure noise too.",
            faiss=0.9,
            verification_status="verified",
        )
    ]
    main = _patch_recall(monkeypatch, hits, crag=True)
    out = main._recall_memory("capital of France")
    assert out is not None
    assert "VERIFIED TRUSTED MEMORY" in out  # trust label preserved
    assert "Paris" in out  # golden strip kept
    assert "closing remarks" not in out  # filler refined away
    assert "- " not in out  # a refined block, not the legacy bullet list


# ── Slice 3: external corrective retrieval (pluggable sources) ───────────────

def test_external_retrieve_aggregates_sources_in_order() -> None:
    cloud = lambda _q: ["cloud doc one", "cloud doc two"]
    web = lambda _q: ["web doc one"]
    docs = external_retrieve("q", [cloud, web])
    assert docs == ["cloud doc one", "cloud doc two", "web doc one"]


def test_external_retrieve_skips_failing_source() -> None:
    def boom(_q: str):
        raise RuntimeError("search api down")

    web = lambda _q: ["survivor doc"]
    docs = external_retrieve("q", [boom, web])
    assert docs == ["survivor doc"]  # one source failing never sinks the rest


def test_external_retrieve_dedupes_and_drops_blank() -> None:
    a = lambda _q: ["Same Doc", "  ", ""]
    b = lambda _q: ["same doc", "unique doc"]  # case/space-insensitive dup of "Same Doc"
    docs = external_retrieve("q", [a, b])
    assert docs == ["Same Doc", "unique doc"]


def test_external_retrieve_caps_per_source() -> None:
    flood = lambda _q: [f"doc {i}" for i in range(10)]
    docs = external_retrieve("q", [flood], per_source_limit=3)
    assert docs == ["doc 0", "doc 1", "doc 2"]


def test_external_retrieve_no_sources_is_empty() -> None:
    assert external_retrieve("q", []) == []


def _patch_recall_external(monkeypatch, hits, *, sources):
    from aios import config
    from aios.api import main

    monkeypatch.setattr(main, "hybrid_search", lambda _q, top_k=3: hits)
    monkeypatch.setattr(config, "CRAG", True)
    monkeypatch.setattr(config, "CRAG_UPPER", 0.6)
    monkeypatch.setattr(config, "CRAG_LOWER", 0.2)
    monkeypatch.setattr(config, "CRAG_EXTERNAL", True)
    monkeypatch.setattr(main, "_crag_external_sources", lambda: sources)
    return main


def test_recall_incorrect_uses_refined_external(monkeypatch) -> None:
    hits = [_Hit("totally unrelated banana note here", faiss=0.05)]
    sources = [lambda _q: ["The quantum entanglement phenomenon links particle states."]]
    main = _patch_recall_external(monkeypatch, hits, sources=sources)
    out = main._recall_memory("quantum entanglement")
    assert out is not None
    assert "EXTERNAL KNOWLEDGE" in out
    assert "entanglement" in out
    assert "banana" not in out  # junk local recall still excluded


def test_recall_incorrect_without_external_returns_none(monkeypatch) -> None:
    hits = [_Hit("totally unrelated banana note here", faiss=0.05)]
    main = _patch_recall_external(monkeypatch, hits, sources=[lambda _q: []])
    assert main._recall_memory("quantum entanglement") is None


def test_recall_ambiguous_combines_local_and_external(monkeypatch) -> None:
    # faiss 0.4 + only partial lexical overlap → score stays in the ambiguous band
    # (not pushed to CORRECT), so local is kept AND external supplements it.
    hits = [_Hit("the alpha section discusses several unrelated longer concepts here", faiss=0.4)]
    sources = [lambda _q: ["External elaboration on the alpha topic with more detail."]]
    main = _patch_recall_external(monkeypatch, hits, sources=sources)
    out = main._recall_memory("alpha topic")
    assert out is not None
    assert "UNVERIFIED PRIOR CHAT MEMORY" in out  # local kept (ambiguous, not dropped)
    assert "EXTERNAL KNOWLEDGE" in out  # external appended


# ── Local-LLM judge (opt-in, AIOS_CRAG_LLM_JUDGE) ───────────────────────────

class _FakeOllama:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def chat(self, messages, *, tools=None, model=None):
        return {"content": self._reply}


def test_crag_llm_judge_parses_score(monkeypatch) -> None:
    from aios.api import main

    monkeypatch.setattr(main, "get_ollama_client", lambda: _FakeOllama("0.82"))
    assert main._crag_llm_judge("q", "passage") == 0.82


def test_crag_llm_judge_extracts_and_clamps(monkeypatch) -> None:
    from aios.api import main

    monkeypatch.setattr(main, "get_ollama_client", lambda: _FakeOllama("I'd say 1.5 relevance"))
    assert main._crag_llm_judge("q", "p") == 1.0  # parsed + clamped to [0,1]


def test_crag_llm_judge_raises_on_unparseable(monkeypatch) -> None:
    import pytest

    from aios.api import main

    monkeypatch.setattr(main, "get_ollama_client", lambda: _FakeOllama("no number at all"))
    with pytest.raises(Exception):  # noqa: B017 - evaluate_retrieval catches & ignores
        main._crag_llm_judge("q", "p")


def test_recall_llm_judge_can_drop_a_strong_local_hit(monkeypatch) -> None:
    # A judge verdict of 0.0 caution-clamps a deterministically-strong hit down to
    # INCORRECT, so the recall is dropped — the judge catches a false-positive.
    from aios import config
    from aios.api import main

    hits = [_Hit("strongly worded but actually off-topic note here", faiss=0.95)]
    monkeypatch.setattr(main, "hybrid_search", lambda _q, top_k=3: hits)
    monkeypatch.setattr(main, "get_ollama_client", lambda: _FakeOllama("0.0"))
    monkeypatch.setattr(config, "CRAG", True)
    monkeypatch.setattr(config, "CRAG_UPPER", 0.6)
    monkeypatch.setattr(config, "CRAG_LOWER", 0.2)
    monkeypatch.setattr(config, "CRAG_LLM_JUDGE", True)
    monkeypatch.setattr(config, "CRAG_EXTERNAL", False)
    assert main._recall_memory("some query") is None


# ── Threshold calibration harness (tune AIOS_CRAG_UPPER/LOWER from real data) ─

def test_calibrate_finds_separating_thresholds() -> None:
    # Cleanly separable: relevant recalls score high, junk scores low → the harness
    # finds thresholds that drop no relevant and accept no junk.
    labeled = [
        (0.85, True), (0.78, True), (0.82, True),
        (0.05, False), (0.10, False), (0.15, False),
    ]
    result = calibrate_thresholds(labeled)
    assert isinstance(result, CalibrationResult)
    assert result.lower <= result.upper
    assert result.false_drop_rate == 0.0  # no relevant recall routed INCORRECT
    assert result.false_accept_rate == 0.0  # no junk routed CORRECT


def test_calibrate_empty_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        calibrate_thresholds([])


def test_calibrate_weight_shifts_lower_to_protect_relevant() -> None:
    # Overlapping scores. Heavily weighting false-drops should push `lower` down so
    # relevant recalls are not dropped (trading more junk into the ambiguous band).
    labeled = [
        (0.30, True), (0.35, True), (0.45, True),
        (0.25, False), (0.40, False), (0.50, False),
    ]
    protect = calibrate_thresholds(labeled, drop_weight=10.0, accept_weight=1.0)
    assert protect.false_drop_rate == 0.0  # the heavily-weighted error is driven out
