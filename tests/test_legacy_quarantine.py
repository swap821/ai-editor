"""Regression guards for the legacy/ tree — quarantine graduated to deletion.

History: legacy/ once held dead scripts that operated on the root
``orchestrator_memory.sqlite`` (P0-2 / P0-5). Step 1 (June) quarantined them
behind refusal prompts and import bans. Step 2 (2026-07-02, operator-approved
coverage-honesty pass) deleted the tree outright: 26 tracked files, zero
importers, containing broken test files that any repo-root collector tripped
over. These guards keep the tree gone and the import ban standing.
"""
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGACY_DIR = PROJECT_ROOT / "legacy"

LEGACY_MODULES = {
    "hybrid_search",
    "ingest_knowledge",
    "ingest_update",
    "extract_text",
    "vector_memory_setup",
    "reset_audit_chain",
}


def test_legacy_tree_stays_deleted() -> None:
    assert not LEGACY_DIR.exists(), (
        "legacy/ was deleted (2026-07-02) after quarantine; it must not "
        "quietly return. Resurrect a module only by wiring and testing it "
        "inside aios/."
    )


def test_legacy_module_names_stay_out_of_live_code() -> None:
    """Live modules must never import the deleted legacy module names."""
    live_dirs = [PROJECT_ROOT / "aios", PROJECT_ROOT / "tests", PROJECT_ROOT / "tools"]
    violations = []
    for directory in live_dirs:
        for py_file in directory.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            for mod in LEGACY_MODULES:
                # Top-level imports only — aios.memory.retrieval.hybrid_search
                # (the LIVE module of the same name) is not a violation.
                patterns = [
                    rf"^\s*import\s+{re.escape(mod)}\b",
                    rf"^\s*from\s+{re.escape(mod)}\s+import\b",
                ]
                if any(re.search(pattern, text, flags=re.MULTILINE) for pattern in patterns):
                    violations.append(f"{py_file.relative_to(PROJECT_ROOT)} imports legacy {mod}")
    assert not violations, (
        "Live code must not import deleted legacy modules:\n" + "\n".join(violations)
    )
