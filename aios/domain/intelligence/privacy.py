"""Privacy boundary evaluation for the Hiring Broker."""
from typing import Sequence
from aios.domain.intelligence.contracts import HiringRequest

LOCAL_PROVIDERS = {"ollama", "local"}

class PrivacyBroker:
    """Evaluates privacy constraints against candidate providers."""

    def filter_eligible_providers(self, request: HiringRequest) -> Sequence[str]:
        """Filter candidate providers based on the data classification.
        
        If the data classification is 'local_only' or 'secret', any cloud provider
        is stripped out of the eligible set.
        """
        classification = request.data_classification
        
        # If the data classification implies extreme sensitivity, only local models are eligible.
        if classification in ("local_only", "secret"):
            return [p for p in request.candidate_providers if p in LOCAL_PROVIDERS]
            
        # For other classifications, all candidates remain eligible at the privacy layer.
        # Cost and capabilities are evaluated later.
        return list(request.candidate_providers)
