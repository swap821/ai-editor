"""
reset_audit_chain.py  —  QUARANTINED / DISABLED

This script was an early-development helper that reset the tamper_audit_trail
 table. It has been quarantined because it operated on the orphaned root
 database `orchestrator_memory.sqlite`, while the live AI-OS audit ledger lives
 in `data/aios_audit.db` and is managed by `aios/security/audit_logger.py`.

Running it changed nothing the product actually verifies, while printing
"Live ledger reset..." — a misleading no-op that could create false confidence
in the tamper-evidence guarantee.

The live, hash-chained, security-critical ledger is intentionally NOT resettable
by a casual script. If a deliberate, audited reset is ever required, build it
against `aios.config.AUDIT_DB_PATH` with full operator review.

This file is retained in `legacy/` for history only.
"""
import sys


def main() -> int:
    print("=" * 72)
    print("QUARANTINED SCRIPT")
    print("=" * 72)
    print()
    print("reset_audit_chain.py is disabled.")
    print()
    print("It previously operated on the orphaned 'orchestrator_memory.sqlite'")
    print("database, NOT the live audit ledger at data/aios_audit.db.")
    print("It has been quarantined as part of renovation P0-2.")
    print()
    print("The live tamper-evident ledger is managed by aios/security/audit_logger.py")
    print("and is intentionally not resettable by a casual script.")
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
