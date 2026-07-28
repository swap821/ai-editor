"""Operator-facing health, tracing and recovery primitives."""

from aios.operations.doctor import DoctorReport, doctor_report
from aios.operations.recovery import (
    BackupDisasterRecoveryAuthority,
    BackupManifest,
    RecoveryError,
    create_backup,
    get_backup_disaster_recovery_authority,
    rebuild_projections,
    restore_backup,
    verify_audit,
    verify_backup,
)

__all__ = [
    "BackupDisasterRecoveryAuthority",
    "BackupManifest",
    "DoctorReport",
    "RecoveryError",
    "create_backup",
    "get_backup_disaster_recovery_authority",
    "doctor_report",
    "rebuild_projections",
    "restore_backup",
    "verify_audit",
    "verify_backup",
]
