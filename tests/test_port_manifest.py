"""The lab-to-product port's manifest (frontend/superbrain-source.json) and
GAGOS's work through the port (2026-11-11, the operator: "GAGOS through the
port").

The manifest records, for every file the port carries, the digest of the
product file as accepted. GAGOS may now change those files; its delivery
updates the manifest as a port from the lab would, and these tests hold the
two to each other."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import aios.maintenance.frontend_static as fs

REPO = Path(__file__).resolve().parents[1]


def test_the_manifest_matches_the_product_it_records() -> None:
    """Every file the manifest records exists in the product with exactly the
    recorded digest. Found false on master 2026-11-11: #533 and #534 both
    changed SuperbrainScene.LEGACY.tsx and the merged file matched neither
    recorded digest; nothing checked it."""
    manifest = json.loads((REPO / fs.PORT_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["version"] == 2
    wrong = []
    for key, digest in manifest["files"].items():
        path = REPO / fs.PORT_ROOT / key
        if not path.is_file():
            wrong.append(f"{key}: missing")
        elif fs.port_digest(path.read_bytes().decode("utf-8")) != digest:
            wrong.append(f"{key}: changed outside the port")
    assert not wrong, wrong


def test_the_digest_is_the_port_tools() -> None:
    # sync-superbrain.mjs, version 2: SHA-256 with CRLF read as LF.
    lf = "export const a = 1;\nexport const b = 2;\n"
    assert fs.port_digest(lf) == hashlib.sha256(lf.encode()).hexdigest()
    assert fs.port_digest(lf.replace("\n", "\r\n")) == fs.port_digest(lf)


def test_rewriting_the_manifest_keeps_its_layout() -> None:
    """The Python rewrite is the port tool's JSON.stringify(m, null, 2) + "\\n":
    a change to one file is a one-line diff, not a reformatted manifest."""
    raw = (REPO / fs.PORT_MANIFEST).read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert json.dumps(json.loads(raw), indent=2, ensure_ascii=False) + "\n" == raw


def _project(tmp_path, files: dict[str, str], *, crlf: bool = False) -> Path:
    for key, text in files.items():
        path = tmp_path / fs.PORT_ROOT / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    manifest = {
        "version": 2,
        "baseline": "accepted product; source SHA-256 normalizes CRLF to LF",
        "files": {key: fs.port_digest(text) for key, text in files.items()},
    }
    text = json.dumps(manifest, indent=2) + "\n"
    (tmp_path / fs.PORT_MANIFEST).write_bytes(
        (text.replace("\n", "\r\n") if crlf else text).encode()
    )
    return tmp_path


def test_a_change_to_a_ported_file_takes_its_new_digest(tmp_path) -> None:
    root = _project(tmp_path, {"lib/a.ts": "a\n", "lib/b.ts": "b\n"})
    out = fs.port_manifest_after(root, {f"{fs.PORT_ROOT}/lib/a.ts": "a2\n"})
    files = json.loads(out)["files"]
    assert files == {
        "lib/a.ts": fs.port_digest("a2\n"),
        "lib/b.ts": fs.port_digest("b\n"),
    }
    assert list(files) == ["lib/a.ts", "lib/b.ts"], "the order is kept"


def test_a_new_file_joins_and_a_removed_one_leaves(tmp_path) -> None:
    root = _project(tmp_path, {"lib/a.ts": "a\n", "lib/b.ts": "b\n"})
    out = fs.port_manifest_after(
        root,
        {
            f"{fs.PORT_ROOT}/lib/a.test.ts": "test\n",
            f"{fs.PORT_ROOT}/lib/b.ts": None,
            f"{fs.PORT_ROOT}/notes.md": "not a kind the port carries\n",
        },
    )
    assert json.loads(out)["files"] == {
        "lib/a.ts": fs.port_digest("a\n"),
        "lib/a.test.ts": fs.port_digest("test\n"),
    }


def test_files_the_port_does_not_carry_leave_it_alone(tmp_path) -> None:
    root = _project(tmp_path, {"lib/a.ts": "a\n"})
    assert fs.port_manifest_after(root, {"frontend/src/workbench/X.jsx": "x\n"}) is None
    assert fs.port_manifest_after(root, {fs.PORT_UNMANAGED: "app\n"}) is None
    assert fs.port_manifest_after(root, {f"{fs.PORT_ROOT}/gone.ts": None}) is None


def test_the_manifests_line_endings_are_kept(tmp_path) -> None:
    root = _project(tmp_path, {"lib/a.ts": "a\n"}, crlf=True)
    out = fs.port_manifest_after(root, {f"{fs.PORT_ROOT}/lib/a.ts": "a2\n"})
    assert "\r\n" in out and "\n" not in out.replace("\r\n", "")


def test_ported_files_are_work_now(tmp_path) -> None:
    for rel in (
        "frontend/src/workbench/Mine.jsx",
        f"{fs.PORT_ROOT}/lib/Owned.ts",
        f"{fs.PORT_ROOT}/ProductOnly.tsx",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("export const x = 1;\n", encoding="utf-8")
    (tmp_path / fs.PORT_MANIFEST).write_text(
        json.dumps({"files": {"lib/Owned.ts": "d"}}), encoding="utf-8"
    )
    assert sorted(fs.editable_frontend_files(tmp_path)) == [
        "frontend/src/superbrain/ProductOnly.tsx",
        "frontend/src/superbrain/lib/Owned.ts",
        "frontend/src/workbench/Mine.jsx",
    ]
