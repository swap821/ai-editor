"""Generate a deterministic manifest SBOM for the shipped source tree."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _python_components(path: Path) -> list[dict[str, str]]:
    components: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = (part.strip() for part in line.split("==", maxsplit=1))
        if not name or not version:
            continue
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name.lower().replace('_', '-')}@{version}",
            }
        )
    return components


def _npm_components(path: Path) -> list[dict[str, str]]:
    lock = json.loads(path.read_text(encoding="utf-8"))
    components: list[dict[str, str]] = []
    for package_path, data in sorted((lock.get("packages") or {}).items()):
        if not package_path or package_path == "":
            continue
        name = package_path.rsplit("/node_modules/", maxsplit=1)[-1]
        if "/" in name and not name.startswith("@"):
            name = name.rsplit("/", maxsplit=1)[-1]
        version = str((data or {}).get("version", ""))
        if not name or not version:
            continue
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:npm/{name}@{version}",
            }
        )
    return components


def build_sbom(repo_root: Path) -> dict[str, object]:
    components = _python_components(repo_root / "requirements.txt")
    components += _npm_components(repo_root / "frontend" / "package-lock.json")
    components.sort(key=lambda item: (str(item["purl"]), str(item["version"])))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:gagos-source-manifest",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "component": {
                "type": "application",
                "name": "gagos",
            },
        },
        "components": components,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = build_sbom(Path(__file__).resolve().parents[1])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.output} with {len(payload['components'])} components")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
