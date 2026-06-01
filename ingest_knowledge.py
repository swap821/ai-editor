import sqlite3
import faiss # pyright: ignore[reportMissingImports]
import warnings
from sentence_transformers import SentenceTransformer # type: ignore

# Suppress warnings
warnings.filterwarnings("ignore")

DB_PATH = 'orchestrator_memory.sqlite'
FAISS_INDEX_PATH = 'vector_index.faiss'
MD_PATH = 'blueprint_text.md'

def ingest():
    print("Starting Knowledge Ingestion...")
    
    # 1. Read the extracted blueprint text
    try:
        with open(MD_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"[ERROR] Could not find {MD_PATH}. Did you extract the PDF?")
        return

    # 2. Chunk the text (Split by double newlines to separate paragraphs cleanly)
    chunks = [c.strip() for c in content.split('\n\n') if len(c.strip()) > 15]
    print(f"- Loaded {len(chunks)} chunks from the blueprint.")

    # 3. Load the AI Embedding Model (it will use your fast local cache)
    print("- Loading AI Embedding Model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')

    # 4. Connect to the databases we built earlier
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    index = faiss.read_index(FAISS_INDEX_PATH)

    # 5. Process and Insert each chunk
    print("- Embedding and storing memories...")
    for chunk in chunks:
        # Generate the 384-dimensional vector for the text
        vector = model.encode([chunk]).astype('float32')
        
        # FAISS index.ntotal gives us the current ID number for this new vector
        current_id = index.ntotal 
        index.add(vector)
        
        # Insert the text and matching vector ID into SQLite
        cursor.execute(
            "INSERT INTO semantic_memory (text_content, vector_id) VALUES (?, ?)", 
            (chunk, current_id)
        )

    # 6. Save the databases
    faiss.write_index(index, FAISS_INDEX_PATH)
    conn.commit()
    conn.close()
    
    print(f"[SUCCESS] Ingested {len(chunks)} architectural memories into the Intelligence Layer!")

if __name__ == '__main__':
    ingest()