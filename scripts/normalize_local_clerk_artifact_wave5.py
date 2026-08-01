#!/usr/bin/env python3
"""Normalize the wave-5 local-clerk artifact, including Phi-4-mini."""

from __future__ import annotations

import json
from pathlib import Path


SOURCE = "https://ollama.com/library/phi4-mini"
MODEL = "phi4-mini:3.8b"


def main() -> int:
    path = Path("release/phase4/local-clerk-candidate-cohort-phi4-wave5-20260801.json")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    for candidate in artifact.get("candidates", []):
        family = candidate["model"].split(":", 1)[0]
        if family == "phi4-mini":
            candidate["source_url"] = SOURCE
            candidate["library_size_gb"] = 2.5

    by_model = {candidate["model"]: candidate for candidate in artifact["candidates"]}
    order = [
        "qwen2.5:3b",
        MODEL,
        "gemma3:4b",
        "qwen2.5:7b",
        "qwen2.5-coder:7b",
        "llama3.1:8b",
    ]
    reasons = {
        "qwen2.5:3b": "Best balanced general clerk default by measured latency and size.",
        MODEL: "Reasoning-focused clerk option; qualified at 2.5 GB but measured slower than the 3B default.",
        "gemma3:4b": "General-purpose fallback with a larger context/resource footprint.",
        "qwen2.5:7b": "Higher-capacity clerk fallback; run one model at a time on 16 GB RAM.",
        "qwen2.5-coder:7b": "Best qualified option for code/document clerical work; heavier and slower.",
        "llama3.1:8b": "High-capacity general clerk fallback; heaviest memory footprint in this cohort.",
    }
    recommendations = []
    for model in order:
        candidate = by_model.get(model)
        if not candidate or candidate.get("status") != "passed":
            continue
        recommendations.append(
            {
                "model": model,
                "role": "local clerk",
                "reason": reasons[model],
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
