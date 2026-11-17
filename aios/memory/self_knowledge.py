"""GAGOS's own documents in its knowledge base (2026-11-13).

Move C on the aliveness map: the knowledge base the counter's corrective
retrieval (CRAG) reads had a door, the operator's upload route, and nothing
ever came through it. At his word ("GAGOS's own docs", 2026-11-13) GAGOS keeps
its own tracked documents there: the README, AGENTS.md, HONEST_STATE.md and the
architecture docs. Each is stored under ``gagos:<path>`` and kept as the
checkout says it is now; a document that is gone is taken out. What the
operator uploads himself is never touched. Everything stays on the laptop, in
the memory database.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

#: The documents GAGOS keeps in its knowledge base, by path in its checkout.
SELF_DOCS = ("README.md", "AGENTS.md", "HONEST_STATE.md")
#: And every architecture document.
SELF_DOC_FOLDER = "docs/architecture"
#: How GAGOS's own documents are named in the knowledge tables.
PREFIX = "gagos:"
#: Where the documents GAGOS writes about itself each hour are named.
GENERATED = "generated"


def self_documents(root: Path) -> list[str]:
    """The documents of *root* GAGOS keeps, as repo-relative paths, sorted."""
    root = Path(root)
    found = [rel for rel in SELF_DOCS if (root / rel).is_file()]
    folder = root / SELF_DOC_FOLDER
    if folder.is_dir():
        found += [
            f"{SELF_DOC_FOLDER}/{path.name}" for path in sorted(folder.glob("*.md"))
        ]
    return sorted(found)


def refresh(
    root: Path, *, ingestor: Any, generated: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Keep GAGOS's documents in *ingestor*'s knowledge tables as they are in
    *root* now, and the documents it *generated* about itself this hour (by
    name, under ``GENERATED/``; 2026-11-17, its face's assessment). Returns
    what changed: ``{"kept", "changed", "removed", "failed"}`` (lists of
    paths; a failure is said with its reason)."""
    root = Path(root)
    kept: list[str] = []
    changed: list[str] = []
    failed: list[str] = []
    documents = [(rel, None) for rel in self_documents(root)] + [
        (f"{GENERATED}/{name}", text) for name, text in (generated or {}).items()
    ]
    present = [rel for rel, _ in documents]
    for rel, text in documents:
        try:
            body = (root / rel).read_bytes() if text is None else text.encode("utf-8")
            out = ingestor.replace(PREFIX + rel, body, "text/markdown")
        except (OSError, ValueError) as exc:
            failed.append(f"{rel}: {exc}")
            continue
        (kept if out.get("unchanged") else changed).append(rel)
    removed = []
    wanted = {PREFIX + rel for rel in present}
    for source in ingestor.list_sources():
        name = str(source.get("filename") or "")
        if name.startswith(PREFIX) and name not in wanted:
            ingestor.delete_source(source["id"])
            removed.append(name[len(PREFIX) :])
    return {"kept": kept, "changed": changed, "removed": removed, "failed": failed}


__all__ = [
    "GENERATED",
    "PREFIX",
    "SELF_DOCS",
    "SELF_DOC_FOLDER",
    "refresh",
    "self_documents",
]
