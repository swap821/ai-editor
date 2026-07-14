"""Operator-facing health, tracing and recovery primitives."""

from aios.operations.doctor import DoctorReport, doctor_report
from aios.operations.recovery import (
    BackupManifest,
    RecoveryError,
    create_backup,
    rebuild_projections,
    restore_backup,
    verify_audit,
    verify_backup,
)

__all__ = [
    "BackupManifest",
    "DoctorReport",
    "RecoveryError",
    "create_backup",
    "doctor_report",
    "rebuild_projections",
    "restore_backup",
    "verify_audit",
    "verify_backup",
]
