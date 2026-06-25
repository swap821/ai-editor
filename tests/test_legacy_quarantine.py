"""Regression tests for P0-2 / P0-5 legacy quarantine.

The legacy/ directory holds dead/orphaned scripts that operated on the root
``orchestrator_memory.sqlite`` database. These tests make sure they cannot be
run accidentally and that they do not touch the live audit ledger.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGACY_DIR = PROJECT_ROOT / "legacy"
LIVE_AUDIT_DB = PROJECT_ROOT / "data" / "aios_audit.db"


@pytest.mark.parametrize(
    "script_name,args,expected_code,expected_substring",
    [
        (
            "reset_audit_chain.py",
            ["--yes"],
            0,
            "QUARANTINED",
        ),
        (
            "vector_memory_setup.py",
            [],
            1,
            "Refusing to initialize",
        ),
        (
            "vector_memory_setup.py",
            ["--yes"],
            0,
            "Vector Memory Environment",
        ),
    ],
)
def test_legacy_script_quarantine(script_name, args, expected_code, expected_substring):
    script = LEGACY_DIR / script_name
    assert script.exists(), f"{script_name} should be quarantined under legacy/"

    before_mtime = LIVE_AUDIT_DB.stat().st_mtime if LIVE_AUDIT_DB.exists() else None

    result = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )

    output = result.stdout + result.stderr
    assert result.returncode == expected_code, (
        f"{script_name} {'should refuse without --yes' if expected_code == 1 else 'should run'}; "
        f"got exit {result.returncode}\n{output}"
    )
    assert expected_substring in output, (
        f"{script_name} output should mention {expected_substring!r}\n{output}"
    )

    if LIVE_AUDIT_DB.exists():
        after_mtime = LIVE_AUDIT_DB.stat().st_mtime
        assert after_mtime == before_mtime, (
            "Legacy script must not touch the live audit ledger "
            f"({LIVE_AUDIT_DB})"
        )


def test_legacy_scripts_not_imported_by_live_code():
    """Live modules must import from ``aios.*``, not the quarantined legacy/."""
    legacy_modules = {
        "hybrid_search",
        "ingest_knowledge",
        "ingest_update",
        "extract_text",
        "vector_memory_setup",
        "reset_audit_chain",
    }
    live_dirs = [PROJECT_ROOT / "aios", PROJECT_ROOT / "tests", PROJECT_ROOT / "tools"]
    violations = []
    for directory in live_dirs:
        for py_file in directory.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            for mod in legacy_modules:
                # Match top-level legacy imports only, not aios.memory.retrieval.hybrid_search.
                patterns = [
                    rf"^\s*import\s+{re.escape(mod)}\b",
                    rf"^\s*from\s+{re.escape(mod)}\s+import\b",
                ]
                if any(re.search(pattern, text, flags=re.MULTILINE) for pattern in patterns):
                    violations.append(f"{py_file.relative_to(PROJECT_ROOT)} imports legacy {mod}")
    assert not violations, "Live code must not import quarantined legacy modules:\n" + "\n".join(violations)
