"""Unused imports in the frontend: the rule the daily frontend worker repairs by
(``aios/maintenance/frontend_imports.py``). Pinned in both directions: what is
unused is found and removed exactly, and anything used -- or merely mentioned --
is never touched."""

from __future__ import annotations

import pytest

from aios.maintenance.frontend_imports import (
    FrontendImportError,
    parse_imports,
    remove_unused_frontend_imports,
    unused_bindings,
)


def _dead(text: str) -> set[str]:
    return {name for names in unused_bindings(text).values() for name in names}


# --------------------------------------------------------------------------- #
# What is unused
# --------------------------------------------------------------------------- #
def test_an_unreferenced_named_import_is_unused_and_a_used_one_is_not() -> None:
    text = "import { useState, useMemo } from 'react';\nexport const x = useMemo(() => 1, []);\n"
    assert _dead(text) == {"useState"}


def test_jsx_type_and_member_use_all_count_as_use() -> None:
    text = (
        "import Panel from './Panel';\n"
        "import type { Props } from './types';\n"
        "import * as api from './api';\n"
        "export function X(p: Props) { return <Panel data={api.load()} />; }\n"
    )
    assert _dead(text) == set()


def test_a_name_only_mentioned_in_a_comment_or_string_is_kept() -> None:
    """Conservative by design: a mention anywhere keeps the import."""
    text = (
        "import { Gauge } from './gauge';\n"
        "import { Meter } from './meter';\n"
        "// Gauge was replaced\n"
        "export const label = 'Meter';\n"
    )
    assert _dead(text) == set()


def test_react_is_never_reported() -> None:
    assert _dead("import React from 'react';\nexport const a = 1;\n") == set()


def test_an_import_inside_a_comment_or_template_is_not_an_import() -> None:
    text = (
        "/*\nimport { Ghost } from './ghost';\n*/\n"
        "const doc = `\nimport { Shadow } from './shadow';\n`;\n"
        "export default doc;\n"
    )
    statements, _ = parse_imports(text)
    assert statements == []


def test_a_clause_it_cannot_parse_is_refused_not_guessed() -> None:
    text = "import { A, /* B, */ C } from './x';\nexport const y = 1;\n"
    statements, refused = parse_imports(text)
    assert statements == [] and len(refused) == 1


def test_an_unclosed_template_refuses_the_whole_file() -> None:
    with pytest.raises(FrontendImportError):
        parse_imports("import { a } from 'b';\nconst t = `unclosed\n")


# --------------------------------------------------------------------------- #
# The rewrite
# --------------------------------------------------------------------------- #
def test_a_single_line_import_keeps_exactly_its_used_names() -> None:
    text = 'import { a, b as c, type T } from "./m"\nexport const v: T = a;\n'
    out = remove_unused_frontend_imports(text, suffix=".ts")
    assert out.removed == ("c",)
    assert out.content == 'import { a, type T } from "./m"\nexport const v: T = a;\n'


def test_typescript_drops_an_emptied_import_because_the_compiler_already_does() -> None:
    text = "import { unused } from './m';\nexport const v = 1;\n"
    out = remove_unused_frontend_imports(text, suffix=".tsx")
    assert out.removed == ("unused",)
    assert out.content == "export const v = 1;\n"


def test_javascript_keeps_an_emptied_import_for_its_side_effects() -> None:
    """In .js/.jsx the module still loads: a CSS module still styles."""
    text = "import styles from './panel.module.css';\nexport const v = 1;\n"
    out = remove_unused_frontend_imports(text, suffix=".jsx")
    assert out.content == "import './panel.module.css';\nexport const v = 1;\n"


def test_an_emptied_type_only_import_is_dropped_everywhere() -> None:
    text = "import type { Unused } from './t';\nexport const v = 1;\n"
    out = remove_unused_frontend_imports(text, suffix=".jsx")
    assert out.content == "export const v = 1;\n"


def test_a_multi_line_import_loses_only_its_unused_lines() -> None:
    text = (
        "import {\n"
        "  Alpha,\n"
        "  Beta, // still here\n"
        "  Gamma,\n"
        "} from './greek';\n"
        "export const v = [Beta, Gamma];\n"
    )
    out = remove_unused_frontend_imports(text, suffix=".ts")
    assert out.removed == ("Alpha",)
    assert "Alpha" not in out.content
    assert "  Beta, // still here\n" in out.content


def test_an_unused_name_sharing_a_line_with_a_used_one_is_skipped_not_mangled() -> None:
    text = "import {\n  Alpha, Beta,\n  Gamma,\n} from './greek';\nexport const v = [Beta, Gamma];\n"
    out = remove_unused_frontend_imports(text, suffix=".ts")
    assert out.removed == ()
    assert out.skipped == ("Alpha",)
    assert out.content == text


def test_crlf_files_keep_their_line_endings() -> None:
    text = "import { a, b } from './m';\r\nexport const v = a;\r\n"
    out = remove_unused_frontend_imports(text, suffix=".ts")
    assert out.content == "import { a } from './m';\r\nexport const v = a;\r\n"


def test_nothing_unused_means_nothing_changes() -> None:
    text = "import { a } from './m';\nexport const v = a;\n"
    out = remove_unused_frontend_imports(text, suffix=".ts")
    assert out.content == text and not out.changed
