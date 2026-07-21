"""Runtime dispatch for local clerical workforce jobs."""

from __future__ import annotations

import json
import time

from aios.core.llm import LLMClient, LLMError
from aios.domain.local_workforce.contracts import LocalJobRequest, LocalJobResult
from aios.domain.local_workforce.validation import ValidationPipeline, ValidationError


class StructuredClericalRuntime:
    """Executes local tasks without granting system authority."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self.max_retries = 3

    def execute_job(self, request: LocalJobRequest) -> LocalJobResult:
        """Execute a clerical job and enforce structure constraints.

        Returns:
            A LocalJobResult representing the strictly validated output, or a
            failure mode if the output could not be safely validated.
        """
        pipeline = ValidationPipeline(request)

        prompt = self._build_prompt(request)
        system = "You are a clerical assistant. Always output valid JSON strictly matching the requested schema."

        start_time = time.time()
        last_error = None

        for _ in range(self.max_retries):
            try:
                # Always enforce JSON mode for structured jobs
                raw_output = self.client.complete(prompt, system=system, json_mode=True)
            except LLMError as exc:
                latency = time.time() - start_time
                return LocalJobResult(
                    job_id=request.job_id,
                    model_id="local",  # Ideally we'd map this, but client abstracts it
                    structured_output=None,
                    schema_valid=False,
                    evidence_references_preserved=False,
                    unsupported_claims=[],
                    latency=latency,
                    status="timeout",
                    failure_reason=str(exc),
                )

            try:
                data, unsupported = pipeline.validate(raw_output)
                latency = time.time() - start_time

                return LocalJobResult(
                    job_id=request.job_id,
                    model_id="local",
                    structured_output=data,
                    schema_valid=True,
                    evidence_references_preserved=True,
                    unsupported_claims=unsupported,
                    latency=latency,
                    status="completed",
                )
            except ValidationError as exc:
                last_error = str(exc)
                # We could append the error to the prompt for a retry here
                prompt += f"\n\nPrevious attempt failed with error: {last_error}. Please fix and output only JSON."

        latency = time.time() - start_time
        return LocalJobResult(
            job_id=request.job_id,
            model_id="local",
            structured_output=None,
            schema_valid=False,
            evidence_references_preserved=False,
            unsupported_claims=[],
            latency=latency,
            status="rejected",
            failure_reason=f"Failed after {self.max_retries} retries. Last error: {last_error}",
        )

    def _build_prompt(self, request: LocalJobRequest) -> str:
        """Construct a rigorous prompt defining the clerical constraints."""
        schema_json = json.dumps(request.required_output_schema, indent=2)
        evidence = "\n".join(f"- {ref}" for ref in request.evidence_references)

        return (
            f"Job Profile: {request.job_profile.value}\n"
            f"Required JSON Schema:\n{schema_json}\n\n"
            f"Evidence Context:\n{evidence}\n\n"
            f"Payload:\n{request.redacted_payload}\n\n"
            "Respond strictly with a single JSON object matching the schema."
        )
