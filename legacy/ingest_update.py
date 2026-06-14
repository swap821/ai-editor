import sqlite3
import faiss
import warnings
from sentence_transformers import SentenceTransformer

warnings.filterwarnings("ignore")

DB_PATH = 'orchestrator_memory.sqlite'
FAISS_INDEX_PATH = 'vector_index.faiss'
NEW_MD_PATH = 'websocket_security_update.md'

def update_memory():
    print("Starting Autonomous Memory Update...")
    
    with open(NEW_MD_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    chunks = [c.strip() for c in content.split('\n\n') if len(c.strip()) > 15]
    print(f"- Loaded {len(chunks)} new chunks.")

    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    index = faiss.read_index(FAISS_INDEX_PATH)

    print("- Embedding and appending new memories...")
    for chunk in chunks:
        vector = model.encode([chunk]).astype('float32')
        current_id = index.ntotal 
        index.add(vector)
        
        cursor.execute(
            "INSERT INTO semantic_memory (text_content, vector_id) VALUES (?, ?)", 
            (chunk, current_id)
        )

    faiss.write_index(index, FAISS_INDEX_PATH)
    conn.commit()
    conn.close()
    
    print(f"[SUCCESS] Appended {len(chunks)} new memories to the Intelligence Layer!")

if __name__ == '__main__':
    update_memory()