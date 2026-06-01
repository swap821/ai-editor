import sys
import json
import sqlite3
import math
from datetime import datetime
import warnings

# Suppress HuggingFace symlink warnings in terminal output
warnings.filterwarnings("ignore")

try:
    import faiss # type: ignore
    from sentence_transformers import SentenceTransformer # type: ignore
except ImportError:
    print(json.dumps([{"text": "Error: Missing FAISS or SentenceTransformers."}]))
    sys.exit(1)

DB_PATH = 'orchestrator_memory.sqlite'
FAISS_INDEX_PATH = 'vector_index.faiss'

def calculate_bm25(query, text):
    query_terms = set(query.lower().split())
    text_terms = text.lower().split()
    score = sum(1 for term in query_terms if term in text_terms)
    return min(score / max(len(query_terms), 1), 1.0)

def hybrid_search(query_text, top_k=3):
    try:
        # 1. Embed the query
        model = SentenceTransformer('all-MiniLM-L6-v2')
        query_vector = model.encode([query_text]).astype('float32')
        
        # 2. FAISS Vector Search
        index = faiss.read_index(FAISS_INDEX_PATH)
        distances, indices = index.search(query_vector, top_k * 2)

        # 3. SQLite Semantic Data & Hybrid Scoring
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        results = []
        now = datetime.now()

        for i, vector_id in enumerate(indices[0]):
            if vector_id == -1: continue
            
            cursor.execute("SELECT id, text_content, timestamp FROM semantic_memory WHERE id = ?", (int(vector_id),))
            row = cursor.fetchone()
            if not row: continue
            
            mem_id, text_content, timestamp_str = row
            try:
                mem_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            except:
                mem_time = now

            # Math: Temporal Decay & Hybrid Score
            delta_t_hours = max((now - mem_time).total_seconds() / 3600.0, 0)
            s_faiss = 1.0 / (1.0 + float(distances[0][i])) # Convert distance to similarity
            s_bm25 = calculate_bm25(query_text, text_content)
            
            temporal_score = math.exp(-0.05 * delta_t_hours)
            final_score = (0.25 * s_bm25) + (0.45 * s_faiss) + (0.30 * temporal_score)
            
            results.append({"id": mem_id, "text": text_content, "score": round(final_score, 4)})

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]
    except Exception as e:
        return [{"text": f"Search Exception: {str(e)}"}]

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps([]))
        sys.exit(0)
    
    query = sys.argv[1]
    hits = hybrid_search(query)
    print(json.dumps(hits))