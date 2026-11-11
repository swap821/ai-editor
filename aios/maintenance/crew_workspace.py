"""A crew agent's workspace (2026-11-11).

The operator chose that GAGOS works like Codex or Claude Code's ultracode: a
lead plans, sub-agents work in parallel, each with file tools (read, search,
edit, write) and one tool of GAGOS's (its sandboxed test run) - "Files +
sandboxed tests". An agent reads and edits files itself, so it cannot be shown
a masked prompt the way a one-shot writer is. Instead it works in a copy:

* the base commit's tracked files under the task's scopes, never the
  operator's checkout, so nothing untracked (keys, data, local notes) is there;
* each text file masked exactly as the workshop masks what it sends
  (:func:`daily_work.mask_lines` with the egress scrubbers as the oracle), its
  placeholders numbered once across the whole copy, so one moved from a file
  into another (a giant file split in two) is restored to the same text;
* files that cannot be masked to text the scrubbers leave unchanged are left
  out and named, never sent half-masked.

When the agent stops, :func:`changes` reads back what it changed, created or
deleted, and :func:`restore` puts the real values back. The copy lives outside
the project; the agent's own tool rules keep it from reading anything else
(measured 2026-11-11: a read outside its directory was refused).
"""

from __future__ import annotations

import io
import re
import subprocess
import tarfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from aios.maintenance.daily_work import (
    MaskingFailed,
    ProposalRefused,
    mask_lines,
    unmask,
)

#: The most placeholders one copy may hold: they are numbered with four digits.
MAX_PLACEHOLDERS = 10_000
_TOKEN = re.compile(r"GAGOSMASKQ+_\d{4}")


@dataclass
class Workspace:
    """*root* holds the masked copy; *shown* is each file's text as written
    there; *mapping* restores every placeholder; *left_out* names the files
    not copied and why."""

    root: Path
    base_commit: str
    shown: dict[str, str] = field(default_factory=dict)
    mapping: dict[str, str] = field(default_factory=dict)
    left_out: dict[str, str] = field(default_factory=dict)


def _tracked(
    project_root: Path, base_commit: str, scopes: Sequence[str]
) -> dict[str, bytes]:
    """The base commit's tracked files under *scopes*, as bytes, from one
    ``git archive`` (no checkout, nothing untracked)."""
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "archive",
            "--format=tar",
            base_commit,
            "--",
            *scopes,
        ],
        capture_output=True,
        check=True,
        timeout=300,
    )
    out: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                data = tar.extractfile(member)
                if data is not None:
                    out[member.name] = data.read()
    return out


def _prefix_free(texts: Sequence[str]) -> str:
    """The shortest placeholder prefix no file already contains."""
    width = 1
    while any(f"GAGOSMASK{'Q' * width}_" in t for t in texts):
        width += 1
    return f"GAGOSMASK{'Q' * width}_"


def build(
    project_root: Path,
    base_commit: str,
    scopes: Sequence[str],
    redact: Callable[[str], str],
    dest: Path,
) -> Workspace:
    """Write the masked copy of *base_commit*'s files under *scopes* into
    *dest* (which must not exist yet or be empty)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        raise ValueError(f"{dest} is not empty")
    ws = Workspace(root=dest, base_commit=base_commit)
    texts: dict[str, str] = {}
    for rel, data in sorted(_tracked(project_root, base_commit, scopes).items()):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            ws.left_out[rel] = "not text"
            continue
        if "\x00" in text:
            ws.left_out[rel] = "not text"
            continue
        texts[rel] = text
    prefix = _prefix_free(list(texts.values()))
    width = prefix.count("Q")
    counter = 0
    for rel, text in texts.items():
        try:
            masked, local = mask_lines(text, redact, min_width=width)
        except MaskingFailed as exc:
            ws.left_out[rel] = f"cannot be masked: {exc}"
            continue
        if redact(masked) != masked:
            ws.left_out[rel] = "the scrubbers would still alter it after masking"
            continue
        if counter + len(local) > MAX_PLACEHOLDERS:
            ws.left_out[rel] = "the copy holds too many placeholders"
            continue
        # One numbering for the whole copy: this file's placeholders renamed in
        # their own order, inside the values too (a later one may wrap earlier).
        renamed: dict[str, str] = {}
        for token in local:
            renamed[token] = f"{prefix}{counter:04d}"
            counter += 1

        def rename(m: re.Match) -> str:
            return renamed.get(m.group(0), m.group(0))

        masked = _TOKEN.sub(rename, masked)
        for token, value in local.items():
            ws.mapping[renamed[token]] = _TOKEN.sub(rename, value)
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(masked.encode("utf-8"))
        ws.shown[rel] = masked
    return ws


def changes(ws: Workspace) -> dict[str, str | None]:
    """What the agent did to the copy, as masked texts: ``{rel: new text}`` for
    each file changed or created, ``{rel: None}`` for each deleted. Writing a
    file the copy left out is refused: GAGOS never showed it, so it cannot be
    judged against what it was."""
    out: dict[str, str | None] = {}
    seen: set[str] = set()
    for path in ws.root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ws.root).as_posix()
        seen.add(rel)
        if rel in ws.left_out:
            raise ProposalRefused(f"the agent wrote {rel}, a file it was not shown")
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProposalRefused(
                f"the agent wrote {rel} as something other than text"
            ) from exc
        if ws.shown.get(rel) != text:
            out[rel] = text
    for rel in ws.shown:
        if rel not in seen:
            out[rel] = None
    return out


def restore(ws: Workspace, changed: dict[str, str | None]) -> dict[str, str | None]:
    """*changed* with every placeholder restored to its real value. A known
    placeholder may move between files or repeat (its value is already in the
    repository); one the copy never held is refused."""
    if not ws.mapping:
        for rel, text in changed.items():
            if text is not None and _TOKEN.search(text):
                raise ProposalRefused(f"{rel} holds a placeholder the copy never had")
        return dict(changed)
    out: dict[str, str | None] = {}
    for rel, text in changed.items():
        out[rel] = (
            None
            if text is None
            else unmask(text, ws.mapping, masked=ws.shown.get(rel, ""), repeat=True)
        )
    return out


__all__ = ["MAX_PLACEHOLDERS", "Workspace", "build", "changes", "restore"]
