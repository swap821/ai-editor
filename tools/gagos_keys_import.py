#!/usr/bin/env python3
"""Move named keys from a .env file into GAGOS's own keystore. Prints names only.

Operator, 2026-10-30: "GAGOS only should [hold] its API keys safely (that's
sovereignty and autonomous)". GAGOS's jobs read their keys from its keystore
(Windows Credential Manager, aios/operations/keystore.py) and from nowhere
else; this moves a key that still lives in a file into it.

  python tools/gagos_keys_import.py --from "frontend/nvdia/.env(aws)" AWS_BEARER_TOKEN_BEDROCK

Only the names given are read, and only names GAGOS knows are stored. The file
is not changed or deleted: once the key is stored, deleting the file is the
operator's own act.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from aios.operations.keystore import (  # noqa: E402
    LOCAL_ONLY,
    NAMES,
    default_keystore,
)


def read_env(path: Path, names: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        if sep and key in names:
            found[key] = value.strip().strip('"').strip("'")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from", dest="source", required=True)
    parser.add_argument("names", nargs="+")
    args = parser.parse_args(argv)
    unknown = [n for n in args.names if n not in NAMES and n not in LOCAL_ONLY]
    if unknown:
        print(f"refused: not GAGOS keys: {', '.join(unknown)}")
        return 2
    found = read_env(Path(args.source), args.names)
    store = default_keystore()
    for name in args.names:
        if found.get(name):
            store.set(name, found[name])
            print(f"stored {name} in GAGOS's keystore (value not shown)")
        else:
            print(f"not in {args.source}: {name}")
    return 0 if all(found.get(n) for n in args.names) else 1


if __name__ == "__main__":
    raise SystemExit(main())
