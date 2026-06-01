import sqlite3
import faiss

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
    
    index = faiss.IndexHNSWFlat(384, 32)
    faiss.write_index(index, 'vector_index.faiss')
    print("- FAISS HNSW Vector Index created successfully.")
    
    print("[SUCCESS] Vector Memory Environment is ready.")

if __name__ == '__main__':
    init_vector_memory()