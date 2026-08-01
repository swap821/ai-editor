#!/usr/bin/env python3
"""Fill official Ollama provenance for every locally-qualified clerk candidate."""

from __future__ import annotations

import json
from pathlib import Path

ARTIFACT = Path(__file__).resolve().parents[1] / "release" / "phase4" / "local-clerk-candidate-cohort-92d871616ce6.json"
SOURCES = {
    "gemma3": "https://ollama.com/library/gemma3",
    "granite3.2": "https://ollama.com/library/granite3.2",
    "llama3.1": "https://ollama.com/library/llama3.1",
    "llama3.2": "https://ollama.com/library/llama3.2",
    "mistral": "https://ollama.com/library/mistral",
    "qwen2.5": "https://ollama.com/library/qwen2.5",
    "qwen2.5-coder": "https://ollama.com/library/qwen2.5-coder",
    "qwen3.5": "https://ollama.com/library/qwen3.5/tags",
    "smollm2": "https://ollama.com/library/smollm2",
}


def main() -> int:
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    for candidate in artifact["candidates"]:
        base = candidate["model"].split(":", 1)[0]
        if base in SOURCES:
            candidate["source_url"] = SOURCES[base]
    by_model = {candidate["model"]: candidate for candidate in artifact["candidates"]}
    for recommendation in artifact["recommendations"]:
        candidate = by_model[recommendation["model"]]
        recommendation["source_url"] = candidate["source_url"]
        recommendation["measured_elapsed_seconds"] = candidate["elapsed_seconds"]
        recommendation["library_size_gb"] = candidate.get("library_size_gb")
    ARTIFACT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passing_recommendations": [item["model"] for item in artifact["recommendations"]]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
