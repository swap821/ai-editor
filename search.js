// search.js
const query = process.argv[2];

if (!query) {
    console.log("Error: Please provide a search query.");
    process.exit(1);
}

async function searchWeb() {
    try {
        // Using Wikipedia's free API for zero-friction setup
        const url = `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(query)}&utf8=&format=json`;
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.query.search.length === 0) {
            console.log(`No results found on the web for "${query}".`);
            return;
        }
        
        console.log(`--- LIVE WEB SEARCH RESULTS FOR: ${query} ---`);
        // Grab the top 3 results
        data.query.search.slice(0, 3).forEach((result, i) => {
            // Clean the raw HTML tags out of the snippet
            const cleanSnippet = result.snippet.replace(/<\/?[^>]+(>|$)/g, "");
            console.log(`\n${i + 1}. [${result.title}]\n${cleanSnippet}`);
        });
    } catch (error) {
        console.error("[NETWORK ERROR] Search failed:", error.message);
    }
}

searchWeb();