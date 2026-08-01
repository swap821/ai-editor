"""Run and record a repeatable local-clerk model qualification cohort.

This is deliberately a thin evidence runner around the production
``LocalModelQualificationAuthority``.  It does not weaken the suite, promote a
model, or change routing policy.  A model is a candidate only when all r15-v2
checks pass; failed candidates remain in the artifact so the shortlist cannot
quietly become a marketing list.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios.core.llm import OllamaClient
from aios.domain.local_workforce.qualifier import (
    LocalModelQualificationAuthority,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SUITE_VERSION = "r15-v2"

# These are the official model-library pages used for candidate selection. The
# qualification result, not the vendor page, decides admission.
SOURCE_URLS = {
    "qwen2.5": "https://ollama.com/library/qwen2.5",
    "qwen2.5-coder": "https://ollama.com/library/qwen2.5-coder",
    "gemma3": "https://ollama.com/library/gemma3",
    "granite3.2": "https://ollama.com/library/granite3.2",
    "llama3.2": "https://ollama.com/library/llama3.2",
    "mistral": "https://ollama.com/library/mistral",
    "smollm2": "https://ollama.com/library/smollm2",
}

# Sizes are the Ollama library/tag sizes used when the cohort was measured;
# they are decision context, not a benchmark claim.
MODEL_SIZES_GB = {
    "gemma3:4b": 3.3,
    "granite3.2:2b": 1.5,
    "mistral:7b": 4.4,
    "qwen2.5:3b": 1.9,
    "qwen2.5:7b": 4.7,
    "qwen2.5-coder:3b": 1.9,
    "qwen2.5-coder:7b": 4.7,
    "llama3.2:3b": 2.0,
    "smollm2:1.7b-instruct-q4_K_M": 1.1,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tip_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _stop_model(model: str) -> None:
    subprocess.run(
        ["ollama", "stop", model],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _source_for(model: str) -> str | None:
    family = model.split(":", 1)[0]
    return SOURCE_URLS.get(family)


def _record_model(model: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = LocalModelQualificationAuthority(
            OllamaClient(model=model, timeout_s=120)
        ).run()
        elapsed = round(time.perf_counter() - started, 2)
        return {
            "model": model,
            "library_size_gb": MODEL_SIZES_GB.get(model),
            "source_url": _source_for(model),
            "status": "passed" if result.passed else "failed",
            "elapsed_seconds": elapsed,
            "schema_validity": result.schema_validity,
            "identifier_preservation": result.identifier_preservation,
            "authority_mutation_attempts": result.authority_mutation_attempts,
            "tool_requests_accepted": result.tool_requests_accepted,
            "secret_reproduction": result.secret_reproduction,
            "unsupported_claim_rate": result.unsupported_claim_rate,
            "timeout_rate": result.timeout_rate,
            "failed_test_ids": [
                item.test_id for item in result.test_results if not item.passed
            ],
        }
    except Exception as exc:  # pragma: no cover - live dependency failure path
        return {
            "model": model,
            "library_size_gb": MODEL_SIZES_GB.get(model),
            "source_url": _source_for(model),
            "status": "error",
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "error": f"{type(exc).__name__}: {exc}",
            "failed_test_ids": [],
        }
    finally:
        _stop_model(model)


def _recommendations(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    passed = {item["model"] for item in candidates if item.get("status") == "passed"}
    descriptions = {
        "granite3.2:2b": (
            "Best lean default for extraction, classification, grouping, and summaries."
        ),
        "qwen2.5:3b": "Best balanced general clerk default by measured latency and size.",
        "gemma3:4b": "General-purpose fallback with a larger context/resource footprint.",
        "qwen2.5:7b": "Higher-capacity clerk fallback; run one model at a time on 16 GB RAM.",
        "qwen2.5-coder:7b": (
            "Best qualified option for code/document clerical work; heavier and slower."
        ),
    }
    ordered = [
        "granite3.2:2b",
        "qwen2.5:3b",
        "gemma3:4b",
        "qwen2.5:7b",
        "qwen2.5-coder:7b",
    ]
    return [
        {
            "model": model,
            "role": "local clerk",
            "reason": descriptions[model],
            "measured_pass": True,
        }
        for model in ordered
        if model in passed
    ]


def _load_base(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_artifact(
    *,
    models: list[str],
    output: Path,
    base_artifact: Path | None,
    tip_sha: str,
) -> None:
    base = _load_base(base_artifact)
    by_model = {
        item["model"]: item for item in base.get("candidates", []) if "model" in item
    }
    for model in models:
        print(f"qualifying {model}", flush=True)
        by_model[model] = _record_model(model)

    candidates = [by_model[model] for model in sorted(by_model)]
    passed = _recommendations(candidates)
    artifact = {
        "schema": "local-clerk-candidate-cohort-v2",
        "generated_at": _now(),
        "tip_sha": tip_sha,
        "hardware": base.get(
            "hardware",
            {
                "machine": platform.node(),
                "cpu": platform.processor(),
                "physical_ram_gb": None,
                "gpu": None,
                "gpu_vram_gb": None,
                "free_ram_at_measurement_gb": None,
            },
        ),
        "suite": {
            "version": SUITE_VERSION,
            "tests_per_model": 20,
            "runner": "scripts/local_clerk_candidate_cohort.py",
            "qualification_is_not_a_model_benchmark": True,
            "bar": "all model cases, repeated reliability, resource, concurrency refusal, and timeout handling must pass",
        },
        "candidates": candidates,
        "recommendations": passed,
        "selection_notes": [
            "Only status=passed models are recommendations.",
            "The suite is a safety/clerical-contract gate, not a general intelligence ranking.",
            "On this 16 GB / 4 GB-VRAM laptop, run one 7B model at a time and prefer 2B-4B defaults.",
            "Web/library metadata is advisory; local qualification is the admission evidence.",
        ],
    }
    if "production_path_probe" in base:
        artifact["production_path_probe"] = base["production_path_probe"]
    artifact["organ_claims"] = {
        "33": "The cohort records locally discovered and qualification-tested model passport candidates.",
        "35": "Only models with a complete r15-v2 pass are listed in recommendations for clerk admission.",
        "37": "Failed candidates remain explicitly recorded with failed test IDs; no model is promoted by size or vendor claims.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": passed}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-artifact", type=Path)
    parser.add_argument("--tip", default=None)
    args = parser.parse_args()
    build_artifact(
        models=args.models,
        output=args.output,
        base_artifact=args.base_artifact,
        tip_sha=args.tip or _tip_sha(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
