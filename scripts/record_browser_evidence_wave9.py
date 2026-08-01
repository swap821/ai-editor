#!/usr/bin/env python3
"""Record the live headed Chrome evidence captured against the local API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "release" / "phase4" / "browser-evidence-live-wave9-20260801.json"
INVENTORY = ROOT / "release" / "phase4" / "local-clerk-inventory-20260801.json"
TIP_SHA = "92d871616ce630ff398cc18e5f9f16e2849713e9"


SURFACES = [
    "live-living-mind.png",
    "live-missions.png",
    "live-self-analysis.png",
    "live-sovereign-state.png",
    "live-knowledge-memory.png",
    "live-policy-control.png",
    "live-services-runtime.png",
    "live-debugger-alignment.png",
    "live-security-audit.png",
    "live-governance.png",
    "live-operations.png",
    "live-history.png",
]


def main() -> int:
    artifact = {
        "schema": "browser-evidence-live-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "tip_sha": TIP_SHA,
        "url": "http://127.0.0.1:5173/",
        "frontend_http_status": 200,
        "backend": {
            "url": "http://127.0.0.1:8000/health",
            "health_status": 200,
            "startup_flags": {
                "host": "127.0.0.1",
                "port": 8000,
                "offline_mode": False,
                "earned_autonomy": True,
                "router_cloud_tasks": ["reasoning", "coding"],
                "token_set": False,
            },
        },
        "browser": {
            "headed": True,
            "engine": "Chrome/150.0.7871.187",
            "connection": "Playwright over CDP to an isolated visible Chrome profile",
            "devtools_port": 9225,
            "profile": "C:\\tmp\\aios-headed-browser-wave9-20260801",
        },
        "measured_ui_observations": [
            "Control plane online",
            "Directive phase idle",
            "Active missions 0",
            "Active workers 0",
            "Models participating 0",
            "Approval none reported",
            "Sovereign spine connected",
            "Governance reports No Council missions recorded",
            "Operations reports no active hiring proposals, local workers, or missions",
            "History reports no operational events",
        ],
        "screenshots": [
            f"release/phase4/browser-runtime-wave9/{name}" for name in SURFACES
        ],
        "operator_attestation": False,
        "mission_and_approval_exercised": False,
        "promoted_to_organ_evidence": False,
        "interpretation": (
            "This is genuine headed-browser runtime evidence that the live frontend "
            "renders measured control-plane state and fail-safe empty states. It does "
            "not prove human operator review, approval interaction, mission execution, "
            "or the cross-provider endurance requirement; the affected organs remain yellow."
        ),
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    attempts = inventory.setdefault("browser_attempt_artifacts", [])
    pointer = "release/phase4/browser-evidence-live-wave9-20260801.json"
    if pointer not in attempts:
        attempts.append(pointer)
    INVENTORY.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": pointer, "promoted": False, "headed": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
