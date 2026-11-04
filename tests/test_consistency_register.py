"""The consistency register's claims are true (2026-11-04, the operator: "I
want u to make my cross-system consistency of my project 10/10 honestly 100%").

``scripts/consistency_audit.py`` scores GAGOS against
``.aios/state/CONSISTENCY_REGISTER.json``. A score is only honest if its rows
are, so this pins:

* every row of the real register holds: its places exist and name their
  symbols, and every guard it claims is a real test;
* the doc's generated status is the register's, not a stale copy;
* the audit refuses a row that claims a guard it does not have, or calls
  itself guarded with none, and counts open rows against the score;
* the scan for hand-written provider lists finds each shape it claims to.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import consistency_audit as ca  # noqa: E402


def test_every_claim_in_the_register_holds() -> None:
    result = ca.audit(ca.load())
    assert result.rows, "the register is empty"
    assert not result.errors, "\n".join(result.errors)


def test_the_doc_shows_the_register_as_it_is() -> None:
    result = ca.audit(ca.load())
    doc = ca.DOC.read_text(encoding="utf-8")
    assert ca.splice(doc, ca.render(result, ca.provider_lists())) == doc, (
        "docs/architecture/CONSISTENCY_REGISTER.md is stale: "
        "run python scripts/consistency_audit.py --write"
    )


def _tree(tmp_path: Path) -> Path:
    (tmp_path / "aios").mkdir()
    (tmp_path / "aios" / "a.py").write_text("CLOUD = {'x'}\n", encoding="utf-8")
    (tmp_path / "aios" / "b.py").write_text("LOCAL = {'y'}\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ab.py").write_text(
        "def test_a_and_b_agree():\n    pass\n", encoding="utf-8"
    )
    return tmp_path


def _row(**kw) -> ca.Row:
    base = dict(
        id="ab",
        fact="a and b agree",
        state="agreed",
        places=("aios/a.py::CLOUD", "aios/b.py::LOCAL"),
        guards=("tests/test_ab.py::test_a_and_b_agree",),
        source=None,
        note="",
    )
    base.update(kw)
    return ca.Row(**base)


def test_a_true_row_is_a_point(tmp_path: Path) -> None:
    result = ca.audit([_row()], _tree(tmp_path))
    assert not result.errors and result.score == 100.0


@pytest.mark.parametrize(
    "row, why",
    [
        (_row(guards=("tests/test_ab.py::test_never_written",)), "has no test"),
        (_row(guards=("tests/test_missing.py::test_x",)), "does not exist"),
        (_row(guards=()), "names none"),
        (_row(places=("aios/a.py::GONE", "aios/b.py::LOCAL")), "no longer names GONE"),
        (_row(places=("aios/a.py::CLOUD",)), "two places or more"),
        (_row(state="single"), "names no source"),
        (_row(state="single", source="aios/c.py"), "not one of its places"),
        (_row(state="fine"), "is not one of"),
    ],
)
def test_a_false_claim_is_an_error_never_a_point(tmp_path: Path, row, why) -> None:
    result = ca.audit([row], _tree(tmp_path))
    assert any(why in e for e in result.errors), result.errors


def test_an_open_row_counts_against_the_score(tmp_path: Path) -> None:
    rows = [_row(), _row(id="cd", state="open", guards=())]
    result = ca.audit(rows, _tree(tmp_path))
    assert not result.errors and result.score == 50.0
    assert [r.id for r in result.open] == ["cd"]


def test_the_scan_finds_every_shape_of_a_provider_list(tmp_path: Path) -> None:
    (tmp_path / "aios").mkdir()
    (tmp_path / "tools").mkdir()
    (tmp_path / "aios" / "lists.py").write_text(
        "\n".join(
            [
                "A = ('bedrock', 'gemini')",
                "B = {'ollama': 1, 'plan': 2}",
                "C = (('openai', 1), ('anthropic', 2))",
                "D = ('bedrock', 'not-a-provider')",
                "PROVIDER_X = 'bedrock'",
            ]
        ),
        encoding="utf-8",
    )
    names = frozenset({"bedrock", "gemini", "ollama", "plan", "openai", "anthropic"})
    found = ca.provider_lists(tmp_path, names)
    assert found == [f"aios/lists.py:{n}" for n in (1, 2, 3, 5)], found


def test_the_register_is_well_formed_json() -> None:
    data = json.loads(ca.REGISTER.read_text(encoding="utf-8"))
    assert set(data) >= {"rows"}
    for row in data["rows"]:
        assert set(row) >= {"id", "fact", "state", "places"}, row
