#!/usr/bin/env python3
"""Normalize any local-clerk cohort into a truthful passing-only release list."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SOURCES = {
    "gemma3": "https://ollama.com/library/gemma3",
    "llama3.1": "https://ollama.com/library/llama3.1",
    "llama3.2": "https://ollama.com/library/llama3.2",
    "mistral": "https://ollama.com/library/mistral",
    "ministral-3": "https://ollama.com/library/ministral-3",
    "qwen2.5": "https://ollama.com/library/qwen2.5",
    "qwen2.5-coder": "https://ollama.com/library/qwen2.5-coder",
    "qwen3": "https://ollama.com/library/qwen3",
    "qwen3.5": "https://ollama.com/library/qwen3.5/tags",
}

SIZES_GB = {
    "qwen2.5:3b": 1.9,
    "gemma3:4b": 3.3,
    "qwen2.5:7b": 4.7,
    "qwen2.5-coder:7b": 4.7,
    "llama3.1:8b": 4.9,
}

REASONS = {
    "qwen2.5:3b": "Best balanced general clerk default by measured latency and size.",
    "gemma3:4b": "General-purpose fallback with a larger context/resource footprint.",
    "qwen2.5:7b": "Higher-capacity clerk fallback; run one model at a time on 16 GB RAM.",
    "qwen2.5-coder:7b": "Best qualified option for code/document clerical work; heavier and slower.",
    "llama3.1:8b": "High-capacity general clerk fallback; heaviest memory footprint in this cohort.",
}

ORDER = list(REASONS)


def normalize(path: Path) -> None:
    artifact: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    candidates = artifact.get("candidates", [])
    for candidate in candidates:
        model = candidate["model"]
        family = model.split(":", 1)[0]
        if family in SOURCES:
            candidate["source_url"] = SOURCES[family]
        if model in SIZES_GB:
            candidate["library_size_gb"] = SIZES_GB[model]

    by_model = {candidate["model"]: candidate for candidate in candidates}
    passed = {
        model for model, candidate in by_model.items() if candidate.get("status") == "passed"
    }
    recommendations = []
    for model in ORDER:
        if model not in passed:
            continue
        candidate = by_model[model]
        recommendations.append(
            {
                "model": model,
                "role": "local clerk",
                "reason": REASONS[model],
                "measured_pass": True,
                "source_url": candidate.get("source_url"),
                "measured_elapsed_seconds": candidate.get("elapsed_seconds"),
                "library_size_gb": candidate.get("library_size_gb"),
            }
        )
    artifact["recommendations"] = recommendations
    artifact["selection_notes"] = [
        "Only status=passed models are recommendations.",
        "The suite is a safety/clerical-contract gate, not a general intelligence ranking.",
        "On this 16 GB / 4 GB-VRAM laptop, run one 7B/8B model at a time and prefer 2B-4B defaults.",
        "Web/library metadata is advisory; local qualification is the admission evidence.",
    ]
    path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(path), "recommendations": [item["model"] for item in recommendations]}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    normalize(args.artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
