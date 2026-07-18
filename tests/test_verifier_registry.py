from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from aios.application.evidence.verifier_registry import (
    VerifierRegistry,
    VerifierRegistryError,
    VerifierSpec,
)
from aios.domain.maintenance.scan_contracts import BoundedScanContract


def _contract(root: Path, *, network_allowed: bool = False) -> BoundedScanContract:
    if network_allowed:
        return BoundedScanContract.model_construct(
            allowed_root=str(root),
            max_files=4,
            max_total_bytes=4096,
            max_file_bytes=1024,
            deadline=10,
            max_findings=4,
            network_allowed=True,
            git_history_allowed=False,
        )
    return BoundedScanContract(
        allowed_root=str(root),
        max_files=4,
        max_total_bytes=4096,
        max_file_bytes=1024,
        deadline=10,
        max_findings=4,
        git_history_allowed=False,
    )


def _spec(root: Path, **updates: str) -> VerifierSpec:
    values = {
        "scanner_id": "controlled-scanner",
        "scanner_version": "1",
        "target_id": "bug.txt",
        "rescan_of": "finding-1",
        "allowed_root": str(root),
    }
    values.update(updates)
    return VerifierSpec(**values)


def _clean_scanner(context):  # noqa: ANN001
    assert context.read_text("bug.txt").replace("\r\n", "\n") == "fixed\n"
    return ()


def test_fixed_maintenance_verifier_returns_structured_evidence(tmp_path: Path) -> None:
    (tmp_path / "bug.txt").write_text("fixed\n", encoding="utf-8")
    registry = VerifierRegistry(scanner_adapters={"controlled-scanner": _clean_scanner})

    result = registry.run(
        _spec(tmp_path),
        contract=_contract(tmp_path),
        scanner=_clean_scanner,
    )

    assert result.status == "completed"
    assert result.passed is True
    assert result.finding_fingerprints == ()
    assert result.argv == (
        "maintenance.rescan",
        "controlled-scanner",
        "1",
        "bug.txt",
        "finding-1",
    )
    assert result.verifier_id == "maintenance.rescan"
    assert result.version == "1"


def test_unknown_scanner_refuses_before_handler_execution(tmp_path: Path) -> None:
    registry = VerifierRegistry(scanner_adapters={})
    with pytest.raises(VerifierRegistryError, match="scanner is not admitted"):
        registry.run(
            _spec(tmp_path),
            contract=_contract(tmp_path),
            scanner=_clean_scanner,
        )


def test_unregistered_scanner_callable_cannot_replay_registered_identity(
    tmp_path: Path,
) -> None:
    registered = lambda _context: ()  # noqa: E731
    caller = lambda _context: ()  # noqa: E731
    registry = VerifierRegistry(scanner_adapters={"controlled-scanner": registered})
    with pytest.raises(VerifierRegistryError, match="scanner adapter mismatch"):
        registry.run(
            _spec(tmp_path),
            contract=_contract(tmp_path),
            scanner=caller,
        )


def test_unknown_verifier_and_version_are_not_constructible(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        VerifierSpec.model_validate(
            {
                **_spec(tmp_path).model_dump(mode="json"),
                "verifier_id": "learned.command",
            }
        )
    with pytest.raises(ValidationError):
        VerifierSpec.model_validate(
            {
                **_spec(tmp_path).model_dump(mode="json"),
                "version": "99",
            }
        )


@pytest.mark.parametrize(
    "field",
    ["command", "image"],
)
def test_learned_command_or_image_is_rejected(tmp_path: Path, field: str) -> None:
    payload = _spec(tmp_path).model_dump(mode="json")
    payload[field] = "python -c unsafe" if field == "command" else "learned:latest"
    with pytest.raises(ValidationError):
        VerifierSpec.model_validate(payload)


def test_root_mismatch_refuses_before_scanning(tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(VerifierRegistryError, match="root does not match"):
        VerifierRegistry(scanner_adapters={"controlled-scanner": _clean_scanner}).run(
            _spec(tmp_path),
            contract=_contract(other),
            scanner=_clean_scanner,
        )


def test_network_enabled_contract_refuses(tmp_path: Path) -> None:
    with pytest.raises(VerifierRegistryError, match="network access"):
        VerifierRegistry(scanner_adapters={"controlled-scanner": _clean_scanner}).run(
            _spec(tmp_path),
            contract=_contract(tmp_path, network_allowed=True),
            scanner=_clean_scanner,
        )


def test_metacharacter_target_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        _spec(tmp_path, target_id="bug.txt;whoami")


def test_metacharacter_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        _spec(tmp_path, allowed_root=f"{tmp_path};whoami")


def test_target_escape_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VerifierRegistryError, match="target escapes"):
        VerifierRegistry(scanner_adapters={"controlled-scanner": _clean_scanner}).run(
            _spec(tmp_path, target_id="..\\outside.txt"),
            contract=_contract(tmp_path),
            scanner=_clean_scanner,
        )


def test_symlink_root_is_rejected_when_supported(tmp_path: Path) -> None:
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this host")

    with pytest.raises(VerifierRegistryError, match="symlink"):
        VerifierRegistry(scanner_adapters={"controlled-scanner": _clean_scanner}).run(
            _spec(link),
            contract=_contract(link),
            scanner=_clean_scanner,
        )
