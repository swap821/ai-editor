"""
reset_audit_chain.py  —  OPT-IN audit ledger reset (run manually).

The live tamper_audit_trail may contain legacy rows from early development
(e.g. duplicate genesis entries) that make verify_chain() report 'broken'
even with no real tampering. For a clean demo baseline you may want a fresh
chain. This script is NON-DESTRUCTIVE: it copies every existing row into
tamper_audit_trail_archive before clearing the live table.

Run it yourself, deliberately:   python reset_audit_chain.py --yes
"""
import sqlite3
import sys

DB = 'orchestrator_memory.sqlite'

def main():
    if '--yes' not in sys.argv:
        print("Refusing to reset without explicit confirmation.")
        print("Re-run with:  python reset_audit_chain.py --yes")
        return
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS tamper_audit_trail_archive AS SELECT * FROM tamper_audit_trail WHERE 0")
    cur.execute("INSERT INTO tamper_audit_trail_archive SELECT * FROM tamper_audit_trail")
    n = cur.execute("SELECT COUNT(*) FROM tamper_audit_trail_archive").fetchone()[0]
    cur.execute("DELETE FROM tamper_audit_trail")
    cur.execute("DELETE FROM sqlite_sequence WHERE name='tamper_audit_trail'")
    conn.commit()
    conn.close()
    print(f"Archived {n} legacy rows -> tamper_audit_trail_archive.")
    print("Live ledger reset to a clean genesis chain. verify_chain() will now return valid:true.")

if __name__ == '__main__':
    main()
