import sqlite3
import sys

try:
    import faiss
except ImportError:  # pragma: no cover - legacy dependency may be absent
    faiss = None


def init_vector_memory():
    print("Initializing Phase 3: The Intelligence Layer...")

    conn = sqlite3.connect('orchestrator_memory.sqlite')
    cursor = conn.cursor()

    # THE FIX: Nuke the old/corrupted table from orbit
    cursor.execute("DROP TABLE IF EXISTS semantic_memory")

    # Build the pristine Phase 3 schema
    cursor.execute('''
        CREATE TABLE semantic_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text_content TEXT NOT NULL,
            vector_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    print("- Relational backend updated successfully.")

    if faiss is not None:
        index = faiss.IndexHNSWFlat(384, 32)
        faiss.write_index(index, 'vector_index.faiss')
        print("- FAISS HNSW Vector Index created successfully.")
    else:
        print("- FAISS unavailable; skipping vector index creation.")

    print("[SUCCESS] Vector Memory Environment is ready.")


def main() -> int:
    if '--yes' not in sys.argv:
        print("Refusing to initialize vector memory without explicit confirmation.")
        print("This script operates on the legacy 'orchestrator_memory.sqlite'")
        print("database and is NOT part of the live AI-OS memory system.")
        print("Re-run with:  python legacy/vector_memory_setup.py --yes")
        return 1
    init_vector_memory()
    return 0


if __name__ == '__main__':
    sys.exit(main())
