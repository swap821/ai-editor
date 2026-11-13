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

from pathlib import Path
from typing import Any

#: The documents GAGOS keeps in its knowledge base, by path in its checkout.
SELF_DOCS = ("README.md", "AGENTS.md", "HONEST_STATE.md")
#: And every architecture document.
SELF_DOC_FOLDER = "docs/architecture"
#: How GAGOS's own documents are named in the knowledge tables.
PREFIX = "gagos:"


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


def refresh(root: Path, *, ingestor: Any) -> dict[str, Any]:
    """Keep GAGOS's documents in *ingestor*'s knowledge tables as they are in
    *root* now. Returns what changed: ``{"kept", "changed", "removed",
    "failed"}`` (lists of paths; a failure is said with its reason)."""
    root = Path(root)
    kept: list[str] = []
    changed: list[str] = []
    failed: list[str] = []
    present = self_documents(root)
    for rel in present:
        try:
            out = ingestor.replace(
                PREFIX + rel, (root / rel).read_bytes(), "text/markdown"
            )
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


__all__ = ["PREFIX", "SELF_DOCS", "SELF_DOC_FOLDER", "refresh", "self_documents"]
