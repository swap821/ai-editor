"""The vulture's dead-import findings are only imports that are really dead.

A finding feeds a repair mission (GAGOS maintaining itself). An import that
looks unused in its own file but is a deliberate re-export, or that another
file takes FROM the module, is alive: removing it breaks its importer. Ruff's
single-file F401 flagged 65 imports in aios/api/main.py on 2026-10-12; 25 of
them were exactly such live re-exports (tests patch `main.scan_and_redact`,
import `_make_failure_hook` from main, ...).
"""

from __future__ import annotations

from pathlib import Path

from aios.maintenance.vulture_sanitation import scan_vulture_code_paths


def _dead(paths, root=None) -> set[str]:
    report = scan_vulture_code_paths(paths, importers_root=root)
    return {f.evidence[0] for f in report.findings if f.kind == "dead_import"}


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_truly_unused_import_is_reported(tmp_path) -> None:
    mod = _write(tmp_path, "pkg/mod.py", "import json\nimport os\nprint(os.sep)\n")
    assert _dead([mod], tmp_path) == {"json"}


def test_a_noqa_reexport_is_not_dead(tmp_path) -> None:
    mod = _write(
        tmp_path,
        "pkg/mod.py",
        "from json import dumps  # noqa: F401 -- re-exported\n"
        "from os import (  # noqa: F401\n    sep,\n    getcwd,\n)\n"
        "from sys import argv  # noqa: E402\n",
    )
    # E402 is not F401: argv is still an unused import.
    assert _dead([mod], tmp_path) == {"argv"}


def test_names_in_dunder_all_are_exported(tmp_path) -> None:
    mod = _write(
        tmp_path, "pkg/mod.py", "from json import dumps, loads\n__all__ = ['dumps']\n"
    )
    assert _dead([mod], tmp_path) == {"loads"}


def test_a_future_import_is_a_directive_not_a_dead_import(tmp_path) -> None:
    mod = _write(tmp_path, "pkg/mod.py", "from __future__ import annotations\n")
    assert _dead([mod], tmp_path) == set()


def test_a_name_another_file_imports_from_the_module_is_alive(tmp_path) -> None:
    mod = _write(tmp_path, "pkg/mod.py", "from json import dumps, loads\n")
    _write(tmp_path, "tests/test_x.py", "from pkg.mod import dumps\n")
    assert _dead([mod], tmp_path) == {"loads"}
    # Without the project root, the local scan cannot know -- and says so.
    assert _dead([mod]) == {"dumps", "loads"}


def test_monkeypatch_targets_and_alias_access_keep_a_name_alive(tmp_path) -> None:
    mod = _write(tmp_path, "pkg/mod.py", "from json import a, b, c, d\n")
    _write(
        tmp_path,
        "tests/test_y.py",
        "import pkg.mod as m\n"
        "from pkg import mod as other\n"
        "def test(monkeypatch):\n"
        "    monkeypatch.setattr('pkg.mod.a', 1)\n"
        "    monkeypatch.setattr(m, 'b', 2)\n"
        "    other.c\n",
    )
    assert _dead([mod], tmp_path) == {"d"}


def test_on_main_the_vulture_spares_what_tests_reach_through_it() -> None:
    root = Path(__file__).resolve().parents[1]
    dead = _dead([root / "aios" / "api" / "main.py"], root)
    for alive in ("scan_and_redact", "gate", "app"):
        assert alive not in dead, alive
