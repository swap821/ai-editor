#!/usr/bin/env python3
"""Remove obsolete no-Ollama wording from generated Phase 6 shortfall artifacts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = "Outside-machine / no Docker / no Ollama / frozen spine / browser-session residuals remain."
NEW = "Outside-machine cloud, frozen-spine, browser-session, and human-red-team residuals remain."


def main() -> int:
    changed = []
    for path in (ROOT / "release" / "phase6" / "organ23-shortfall.json", ROOT / "release" / "phase6" / "organ23-shortfall.md"):
        text = path.read_text(encoding="utf-8")
        if OLD in text:
            path.write_text(text.replace(OLD, NEW), encoding="utf-8")
            changed.append(path.as_posix())
    print({"changed": changed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
