// knowledgeGraph.js
export async function initGraphDB(db) {
    await db.run(`
        CREATE TABLE IF NOT EXISTS knowledge_graph (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_node TEXT NOT NULL,
            relation TEXT NOT NULL,
            target_node TEXT NOT NULL,
            UNIQUE(source_node, relation, target_node)
        )
    `);
}

export async function addGraphEdge(db, source, relation, target) {
    try {
        await db.run(
            `INSERT OR IGNORE INTO knowledge_graph (source_node, relation, target_node) VALUES (?, ?, ?)`,
            [source.toLowerCase(), relation.toUpperCase(), target.toLowerCase()]
        );
        return `Successfully mapped concept: [${source}] -> (${relation}) -> [${target}]`;
    } catch (error) {
        return `Failed to map knowledge: ${error.message}`;
    }
}

export async function queryGraph(db, entity) {
    try {
        const results = await db.all(
            `SELECT * FROM knowledge_graph WHERE source_node = ? OR target_node = ?`,
            [entity.toLowerCase(), entity.toLowerCase()]
        );
        
        if (results.length === 0) return `No mapped relationships found for "${entity}".`;
        
        let report = `--- KNOWLEDGE GRAPH FOR: ${entity} ---\n`;
        results.forEach(row => {
            report += `* ${row.source_node} --[${row.relation}]--> ${row.target_node}\n`;
        });
        return report;
    } catch (error) {
        return `Graph query failed: ${error.message}`;
    }
}