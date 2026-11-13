"""A placeholder in a review stands for one value (2026-11-13).

A first test's review shows the module under its mask, then the new test under
the module's mask, and then hides what the writer added behind placeholders of
its own. Those were numbered under the module's prefix again whenever the
module's placeholders did not occur in the test, so ``GAGOSMASKQ_0000`` meant
a name in the module's doc comment and, in the test, the reset function the
test imports. Claude rejected the correct test gd-f98e938baf for importing
"what appears in the module only in a doc comment". Pinned without a model:
a scrubber that hides one name in the module's comment and the other in the
test's import list.
"""

from __future__ import annotations

import re

from aios.maintenance.daily_work import MASK_TOKEN, MISSING_TEST, Finding
from tools import gagos_daily as tool

MODULE = (
    "/**\n"
    " * product-only SuperbrainReactiveEffects renders it\n"
    " */\n"
    "export function __resetSpineFlashBridgeForTests() {}\n"
)
TEST = (
    "import {\n"
    "  __resetSpineFlashBridgeForTests,\n"
    "} from './spineFlashBridge';\n"
    "beforeEach(() => {\n"
    "  __resetSpineFlashBridgeForTests();\n"
    "});\n"
)


def _redact(text: str) -> str:
    """Hides the name in the comment, and the reset function where it stands
    alone in an import list: what the privacy filter did."""
    text = text.replace("SuperbrainReactiveEffects", "[REDACTED]")
    return re.sub(r"(?m)^  __resetSpineFlashBridgeForTests,$", "  [REDACTED],", text)


def _shown(monkeypatch) -> str:
    monkeypatch.setattr(tool, "mask_redact", _redact)
    p = {
        "proposal_id": "gd-0000000000",
        "rel": "frontend/src/workbench/spineFlashBridge.test.ts",
        "base_text": MODULE,
        "new_text": TEST,
        "facts": "[]",
        "group_id": None,
        "sandbox": None,
        "prescreen": None,
    }
    return tool.review_evidence(p, Finding(p["rel"], MISSING_TEST, ()))


def test_the_module_and_the_added_spans_never_share_a_placeholder(
    monkeypatch,
) -> None:
    prompt = _shown(monkeypatch)
    module_tokens = set(MASK_TOKEN.findall(prompt.split("beforeEach")[0]))
    comment = next(line for line in prompt.splitlines() if "product-only" in line)
    (in_comment,) = MASK_TOKEN.findall(comment)
    imported = next(
        line
        for line in prompt.splitlines()
        if MASK_TOKEN.search(line) and line.strip().endswith(",")
    )
    (in_import,) = MASK_TOKEN.findall(imported)
    assert in_comment != in_import, module_tokens
    # Each shows its own kind: the added one is announced as the writer's.
    assert "hides something the writer added" in prompt
