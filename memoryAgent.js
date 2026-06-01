import { exec } from 'child_process';
import util from 'util';

const execAsync = util.promisify(exec);

export async function hybridMemorySearch(db, query, topK = 3) {
    if (!query) return [];
    
    console.log(`[MEMORY] Initiating Phase 3 Hybrid Search for: "${query}"`);
    
    try {
        // We use JSON.stringify to safely escape the query string for the command line
        const safeQuery = JSON.stringify(query);
        const { stdout } = await execAsync(`python hybrid_search.py ${safeQuery}`);
        
        const results = JSON.parse(stdout.trim());
        return results;
    } catch (error) {
        console.error("[MEMORY ERROR] Failed to execute FAISS hybrid search:", error.message);
        return [];
    }
}