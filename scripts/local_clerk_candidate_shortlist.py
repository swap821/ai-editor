"""Normalize a local-clerk cohort into an explicit, passing-only shortlist.

The live runner records observations. This small release step adds the
hardware-aware policy labels and ensures every passing candidate is visible;
it never converts a failed or missing qualification into an admission.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SOURCES = {
    "gemma3": "https://ollama.com/library/gemma3",
    "granite3.2": "https://ollama.com/library/granite3.2",
    "llama3.1": "https://ollama.com/library/llama3.1",
    "llama3.2": "https://ollama.com/library/llama3.2",
    "mistral": "https://ollama.com/library/mistral",
    "qwen2.5": "https://ollama.com/library/qwen2.5",
    "qwen2.5-coder": "https://ollama.com/library/qwen2.5-coder",
    "smollm2": "https://ollama.com/library/smollm2",
}

SIZES_GB = {
    "llama3.1:8b": 4.9,
}

REASONS = {
    "gemma3:4b": "General-purpose fallback with a larger context/resource footprint.",
    "llama3.1:8b": "High-capacity general clerk fallback; heaviest memory footprint in this cohort.",
    "qwen2.5:3b": "Best balanced general clerk default by measured latency and size.",
    "qwen2.5:7b": "Higher-capacity clerk fallback; run one model at a time on 16 GB RAM.",
    "qwen2.5-coder:7b": "Best qualified option for code/document clerical work; heavier and slower.",
    "granite3.2:2b": "Lean extraction/classification candidate; keep only when repeated runs remain passing.",
}

ORDER = [
    "qwen2.5:3b",
    "gemma3:4b",
    "qwen2.5:7b",
    "qwen2.5-coder:7b",
    "llama3.1:8b",
    "granite3.2:2b",
]


def _source(model: str) -> str | None:
    return SOURCES.get(model.split(":", 1)[0])


def refresh(path: Path) -> None:
    artifact: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    candidates = artifact.get("candidates", [])
    for candidate in candidates:
        candidate.setdefault("source_url", _source(candidate["model"]))
        if candidate["model"] in SIZES_GB:
            candidate.setdefault("library_size_gb", SIZES_GB[candidate["model"]])

    passed = {
        candidate["model"]
        for candidate in candidates
        if candidate.get("status") == "passed"
    }
    artifact["recommendations"] = [
        {
            "model": model,
            "role": "local clerk",
            "reason": REASONS[model],
            "measured_pass": True,
        }
        for model in ORDER
        if model in passed
    ]
    artifact["selection_notes"] = [
        "Only status=passed models are recommendations.",
        "The suite is a safety/clerical-contract gate, not a general intelligence ranking.",
        "On this 16 GB / 4 GB-VRAM laptop, run one 7B/8B model at a time and prefer 2B-4B defaults.",
        "Web/library metadata is advisory; local qualification is the admission evidence.",
    ]
    path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    refresh(args.artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
