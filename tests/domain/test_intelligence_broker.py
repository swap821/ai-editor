"""Tests for the Frontier Intelligence Hiring Broker."""
import pytest
from aios.domain.intelligence.contracts import HiringRequest
from aios.domain.intelligence.broker import HiringBroker
from aios.domain.intelligence.privacy import PrivacyBroker

@pytest.fixture
def base_request():
    return HiringRequest(
        problem_id="prob-1",
        mission_id="miss-1",
        purpose="reasoning",
        task_class="coding",
        required_capabilities=["reasoning"],
        data_classification="public",
        context_manifest=[],
        privacy_budget="high",
        cost_budget="high",
        latency_budget=10000,
        candidate_providers=["ollama", "bedrock", "gemini"],
        verification_requirements=[]
    )

def test_privacy_broker_allows_all_for_public(base_request):
    broker = PrivacyBroker()
    eligible = broker.filter_eligible_providers(base_request)
    assert set(eligible) == {"ollama", "bedrock", "gemini"}

def test_privacy_broker_strips_cloud_for_local_only(base_request):
    req = base_request.model_copy(update={"data_classification": "local_only"})
    broker = PrivacyBroker()
    eligible = broker.filter_eligible_providers(req)
    assert set(eligible) == {"ollama"}

def test_hiring_broker_selects_cheapest_capable(base_request):
    broker = HiringBroker()
    decision = broker.evaluate_request(base_request)
    # ollama is "free", others are "high" or "low"
    assert decision.selected_provider == "ollama"
    assert decision.human_approval_required is False

def test_hiring_broker_respects_capabilities(base_request):
    req = base_request.model_copy(update={"required_capabilities": ["frontier"]})
    broker = HiringBroker()
    decision = broker.evaluate_request(req)
    # ollama lacks "frontier"
    # gemini is "low" cost, bedrock is "high" cost. gemini wins.
    assert decision.selected_provider == "gemini"
    assert "bedrock" in decision.fallback_order
    assert "ollama" not in decision.eligible_providers

def test_hiring_broker_respects_cost_budget(base_request):
    # Needs frontier, but cost budget is free
    req = base_request.model_copy(update={
        "required_capabilities": ["frontier"],
        "cost_budget": "free"
    })
    broker = HiringBroker()
    decision = broker.evaluate_request(req)
    assert decision.selected_provider is None
    assert "No candidate provider meets" in decision.reason

def test_hiring_broker_human_approval_for_confidential(base_request):
    # Needs frontier (cloud required), data is confidential
    req = base_request.model_copy(update={
        "required_capabilities": ["frontier"],
        "data_classification": "confidential"
    })
    broker = HiringBroker()
    decision = broker.evaluate_request(req)
    assert decision.selected_provider is not None
    assert decision.human_approval_required is True
