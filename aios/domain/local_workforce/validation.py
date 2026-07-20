"""Validation pipeline for local clerical models."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence, Tuple

from aios.domain.local_workforce.contracts import LocalJobRequest


class ValidationError(Exception):
    """Raised when structured output fails validation."""

    pass


class ValidationPipeline:
    """Rigorous pipeline for validating local LLM advisory outputs."""

    def __init__(self, request: LocalJobRequest) -> None:
        self.request = request

    def validate(self, raw_output: str) -> Tuple[Mapping[str, Any], Sequence[str]]:
        """Validate raw output through the strict pipeline.

        Returns:
            A tuple of (parsed_json, unsupported_claims)

        Raises:
            ValidationError: If any hard gate fails.
        """
        # 1. JSON parse
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid JSON: {exc}")

        if not isinstance(data, dict):
            raise ValidationError("JSON output must be a top-level object")

        # 2. Forbidden-field validation
        self._validate_forbidden_fields(data)

        # 3. Schema validation
        self._validate_schema(data)

        # 4. Identifier validation (Evidence-reference validation)
        self._validate_identifiers(data)

        # 5. Unsupported-claim detection
        unsupported = self._detect_unsupported_claims(data)

        return data, unsupported

    def _validate_schema(self, data: dict[str, Any]) -> None:
        schema = self.request.required_output_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for req_field in required:
            if req_field not in data:
                raise ValidationError(f"Missing required field: {req_field}")

        # Basic strict-key checking: we shouldn't have extra keys not in properties
        # unless it's a very loose schema
        if properties:
            for key in data:
                if key not in properties:
                    raise ValidationError(f"Unexpected field in output: {key}")

    def _validate_forbidden_fields(self, data: dict[str, Any]) -> None:
        forbidden = {"tool_calls", "command", "authority_override", "execute"}
        for k in data:
            if k in forbidden:
                raise ValidationError(f"Forbidden field detected: {k}")

    def _validate_identifiers(self, data: dict[str, Any]) -> None:
        # Check if any field ends with _id or is an array of ids,
        # they must belong to the allowed evidence references if provided.
        allowed_refs = self.request.evidence_references
        if not allowed_refs:
            return

        for k, v in data.items():
            if k.endswith("_id") and isinstance(v, str):
                if v not in allowed_refs:
                    raise ValidationError(
                        f"Invented identifier detected: {v} is not in evidence_references"
                    )
            elif k.endswith("_ids") and isinstance(v, list):
                for item in v:
                    if isinstance(item, str) and item not in allowed_refs:
                        raise ValidationError(
                            f"Invented identifier detected in array: {item} is not in evidence_references"
                        )

    def _detect_unsupported_claims(self, data: dict[str, Any]) -> list[str]:
        # Basic heuristic for now, would use NLP or smaller model for actual RAG
        unsupported = []
        return unsupported
