"""A test in the sandbox must be able to import the module beside it.

`training_ground/` has an `__init__.py`, so it is a package, and the agent's
verify command runs from the repo root. Under pytest's default `prepend` import
mode that puts the package's PARENT on `sys.path` and never the package dir, so
a test written the way a developer writes one --

    from calculator import Calculator

-- raised ModuleNotFoundError, while the package-qualified spelling worked.

This decided golden missions. `multi-module`'s prompt is the only one naming the
package path, and it passed 3/3 on gemini-3.7-flash; `tdd-workflow` (no import
guidance) failed 3/3 with `No module named 'calculator'`. The model's code was
correct and the sandbox could not import it -- scored as a capability failure.

`training_ground/conftest.py` now puts the sandbox dir on `sys.path`. Nothing
about the missions, the verifier or the pass criteria changed.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = ROOT / "training_ground"


@pytest.fixture
def sibling_module(tmp_path):
    """Write a module and a test beside it in the real sandbox, then clean up."""
    mod = SANDBOX / "_import_probe_mod.py"
    written: list[Path] = [mod]
    mod.write_text("VALUE = 41\n", encoding="utf-8")

    def make_test(import_line: str) -> Path:
        test = SANDBOX / "test__import_probe.py"
        test.write_text(
            f"{import_line}\n\n\ndef test_value():\n    assert VALUE == 41\n",
            encoding="utf-8",
        )
        written.append(test)
        return test

    yield make_test
    for path in written:
        path.unlink(missing_ok=True)


def _run(test_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", str(test_path), "-q"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120,
    )


def test_a_bare_sibling_import_resolves(sibling_module) -> None:
    """The spelling a developer writes, and the one the models wrote."""
    result = _run(sibling_module("from _import_probe_mod import VALUE"))

    assert result.returncode == 0, (
        "a test cannot import the module sitting beside it:\n"
        f"{result.stdout[-400:]}"
    )


def test_the_package_qualified_import_still_resolves(sibling_module) -> None:
    """The spelling multi-module's prompt names. Both must work."""
    result = _run(sibling_module("from training_ground._import_probe_mod import VALUE"))

    assert result.returncode == 0, (
        "the package-qualified import broke:\n" f"{result.stdout[-400:]}"
    )


def test_the_conftest_states_why() -> None:
    """A bare sys.path insertion with no reason invites deletion."""
    text = (SANDBOX / "conftest.py").read_text(encoding="utf-8")

    assert "sys.path" in text
    assert "ModuleNotFoundError" in text, "the conftest does not say what it fixes"
