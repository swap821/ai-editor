#!/usr/bin/env python3
"""Normalize the wave-8 local-clerk artifact, including Qwen2.5 1.5B."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "release" / "phase4" / "local-clerk-candidate-cohort-qwen15-wave8-20260801.json"


def main() -> int:
    artifact = json.loads(PATH.read_text(encoding="utf-8"))
    metadata = {
        "qwen2.5:1.5b": ("https://ollama.com/library/qwen2.5%3A1.5b", 0.986),
        "qwen2.5:3b": ("https://ollama.com/library/qwen2.5", 1.9),
        "phi4-mini:3.8b": ("https://ollama.com/library/phi4-mini", 2.5),
        "gemma3:4b": ("https://ollama.com/library/gemma3", 3.3),
        "qwen2.5:7b": ("https://ollama.com/library/qwen2.5", 4.7),
        "qwen2.5-coder:7b": ("https://ollama.com/library/qwen2.5-coder", 4.7),
        "llama3.1:8b": ("https://ollama.com/library/llama3.1", 4.9),
    }
    reasons = {
        "qwen2.5:1.5b": "Fastest/lightest qualified clerk for simple, low-latency clerical work; lower capacity than the 3B default.",
        "qwen2.5:3b": "Best balanced general clerk default by measured latency and size.",
        "phi4-mini:3.8b": "Reasoning-focused clerk option; qualified at 2.5 GB but measured slower than the 3B default.",
        "gemma3:4b": "General-purpose fallback with a larger context/resource footprint.",
        "qwen2.5:7b": "Higher-capacity clerk fallback; run one model at a time on 16 GB RAM.",
        "qwen2.5-coder:7b": "Best qualified option for code/document clerical work; heavier and slower.",
        "llama3.1:8b": "High-capacity general clerk fallback; heaviest memory footprint in this cohort.",
    }
    for candidate in artifact.get("candidates", []):
        if candidate["model"] in metadata:
            candidate["source_url"], candidate["library_size_gb"] = metadata[candidate["model"]]
    by_model = {candidate["model"]: candidate for candidate in artifact.get("candidates", [])}
    order = list(metadata)
    artifact["recommendations"] = [
        {
            "model": model,
            "role": "local clerk",
            "reason": reasons[model],
            "measured_pass": True,
            "source_url": by_model[model]["source_url"],
            "measured_elapsed_seconds": by_model[model].get("elapsed_seconds"),
            "library_size_gb": by_model[model]["library_size_gb"],
        }
        for model in order
        if model in by_model and by_model[model].get("status") == "passed"
    ]
    artifact["selection_notes"] = [
        "Only status=passed models are recommendations.",
        "The suite is a safety/clerical-contract gate, not a general intelligence ranking.",
        "On this 16 GB / 4 GB-VRAM laptop, run one 7B/8B model at a time and prefer 1.5B-4B defaults.",
        "Web/library metadata is advisory; local qualification is the admission evidence.",
    ]
    PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(PATH), "recommendations": [item["model"] for item in artifact["recommendations"]]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
