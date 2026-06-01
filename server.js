import 'dotenv/config'; 
import express from 'express';
import cors from 'cors';
import { exec } from 'child_process';
import { initDB } from './database.js';
import { logAuditEntry, verifyAuditChain } from './auditLogger.js';
import { analyzeAndLogMistake } from './reflectionEngine.js';
import { hybridMemorySearch } from './memoryAgent.js';
import { scanAndRedactSecrets } from './secretScanner.js';
import { validateCommand } from './securityGateway.js';
import { createPreActionSnapshot, rollbackToLastSnapshot } from './rollbackEngine.js';
import { initGraphDB, addGraphEdge, queryGraph } from './knowledgeGraph.js';

const app = express();
app.use(cors());
app.use(express.json());

// Silent JSON Extraction 
function extractJSON(text) {
  const cleaned = text.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
  try { 
    return JSON.parse(cleaned); 
  } catch (e) {
    const firstOpen = cleaned.indexOf('{');
    const lastClose = cleaned.lastIndexOf('}');
    if (firstOpen !== -1 && lastClose !== -1 && lastClose > firstOpen) {
      try { return JSON.parse(cleaned.substring(firstOpen, lastClose + 1)); } catch (innerError) {}
    }
    return null; 
  }
}

// --- Promise-based Local Execution Helper ---
const executeLocalCommand = (command) => {
  return new Promise((resolve) => {
    const shellOptions = process.platform === 'win32' ? { shell: 'powershell.exe' } : {};
    exec(command, { timeout: 30000, maxBuffer: 1024 * 1024 * 10, ...shellOptions }, (error, stdout, stderr) => {
      let output = stdout || '';
      if (stderr) output += '\n' + stderr;
      if (error) output = (output.trim() !== '' ? output : error.message);
      resolve(output.trim() || "Task completed successfully with no output.");
    });
  });
};

const workspaceTools = [
  {
    toolSpec: {
      name: "create_snapshot",
      description: "Take a system snapshot BEFORE running risky terminal commands or editing files.",
      inputSchema: { json: { type: "object", properties: {} } } // FIX: Removed empty required array
    }
  },
  {
    toolSpec: {
      name: "rollback_workspace",
      description: "If a command fails or breaks the system, use this to instantly undo all changes.",
      inputSchema: { json: { type: "object", properties: {} } } // FIX: Removed empty required array
    }
  },
  {
    toolSpec: {
      name: "map_knowledge",
      description: "Permanently map a relationship between two concepts/files (e.g., 'server.js', 'DEPENDS_ON', 'express').",
      inputSchema: {
        json: {
          type: "object",
          properties: {
            source: { type: "string" },
            relation: { type: "string", description: "Uppercase relationship (e.g., IMPORTS, DEPENDS_ON, CONTAINS)" },
            target: { type: "string" }
          },
          required: ["source", "relation", "target"]
        }
      }
    }
  },
  {
    toolSpec: {
      name: "query_knowledge",
      description: "Check the Knowledge Graph for relationships connected to a specific entity or file.",
      inputSchema: {
        json: {
          type: "object",
          properties: { entity: { type: "string" } },
          required: ["entity"]
        }
      }
    }
  },
  {
    toolSpec: {
      name: "execute_terminal",
      description: "Execute standard development workspace tasks such as file management, directory layout configurations, project initialization, or compiler build routines.",
      inputSchema: {
        json: {
          type: "object",
          properties: {
            commands: { type: "array", items: { type: "string" }, description: "Array of workspace development commands." },
            explanation: { type: "string", description: "Technical context describing what the workspace commands perform." }
          },
          required: ["commands", "explanation"]
        }
      }
    }
  },
  {
    toolSpec: {
      name: "read_directory",
      description: "Scan a directory to see what files and folders already exist before attempting to create or modify them.",
      inputSchema: {
        json: {
          type: "object",
          properties: { path: { type: "string", description: "The relative path to scan." } },
          required: ["path"]
        }
      }
    }
  },
  {
    toolSpec: {
      name: "read_file",
      description: "Read the exact contents of an existing file so you can analyze the code before suggesting modifications.",
      inputSchema: {
        json: {
          type: "object",
          properties: { filepath: { type: "string", description: "The relative path of the file to read." } },
          required: ["filepath"]
        }
      }
    }
  },
  {
    toolSpec: {
      name: "search_internet",
      description: "Search the web for real-time facts, technical documentation, and general knowledge.",
      inputSchema: {
        json: {
          type: "object",
          properties: { query: { type: "string", description: "The precise search query to look up." } },
          required: ["query"]
        }
      }
    }
  }
];

app.post('/api/generate', async (req, res) => {
  const { messages, modelId } = req.body; 
  const region = process.env.AWS_REGION || "us-east-1";
  const bearerToken = process.env.AWS_BEARER_TOKEN_BEDROCK?.trim();

  if (!bearerToken) return res.status(500).json({ text: "AWS Error: Missing API Key." });

  let latestQuery = "";
  if (messages && messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.role === "user" && lastMsg.content[0].text) {
          latestQuery = lastMsg.content[0].text;
          const sessionId = "session-alpha"; 
          await db.run(
            `INSERT INTO episodic_memory (session_id, role, content) VALUES (?, ?, ?)`,
            [sessionId, "user", latestQuery]
          ).catch(e => {});
      }
  }

  const recalledMemories = await hybridMemorySearch(db, latestQuery, 3);
  let memoryContextBlock = "";
  if (recalledMemories.length > 0) {
      memoryContextBlock = "\n--- AUTHORITATIVE PROJECT KNOWLEDGE BASE ---\n";
      recalledMemories.forEach(m => {
          memoryContextBlock += `${m.content}\n\n`;
      });
      memoryContextBlock += "--------------------------------------------\n";
  }

  const systemPrompt = `You are an elite, fully autonomous Agentic AI integrated directly into an IDE workspace.
${memoryContextBlock}
CRITICAL KNOWLEDGE DIRECTIVE:
If the user asks a question about the project architecture, specifications, or blueprints, YOU MUST base your answer strictly on the 'AUTHORITATIVE PROJECT KNOWLEDGE BASE' provided above. Do not hallucinate or use generalized industry knowledge (e.g., do not talk about hardware RAM if asked about the software memory architecture).

CRITICAL DIRECTIVES FOR AGENTIC OPERATION:
1. NEVER guess what files exist. Always use the 'read_directory' tool to scan the workspace.
2. NEVER guess the contents of a file. Always use the 'read_file' tool.
3. The user is on Windows using PowerShell. 
   - NEVER use 'touch'. Use: New-Item -ItemType File -Force -Path 'filename.ext'
   - NEVER use 'echo'. Use: Set-Content -Path 'filename.ext' -Value 'your code'

If outputting UI code directly to the editor, respond ONLY with JSON:
{ "text": "Summary", "code": "Code string", "language": "html" }

If executing terminal/workspace actions, invoke the appropriate tool.`;

  try {
    let isAgentWorking = true;
    let loopCount = 0;
    const MAX_STEPS = 5; 

    const systemBlock = [
      { text: systemPrompt },
      { cachePoint: { type: "default" } } 
    ];

    while (isAgentWorking && loopCount < MAX_STEPS) {
      loopCount++;
      console.log(`[AGENT LOOP] Iteration ${loopCount}...`);

      const bedrockResponse = await fetch(`https://bedrock-runtime.${region}.amazonaws.com/model/${modelId}/converse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${bearerToken}` },
        body: JSON.stringify({
          messages: messages, 
          system: systemBlock,
          toolConfig: { tools: workspaceTools },
          inferenceConfig: { maxTokens: 2000, temperature: 0.3 }
        })
      });

      if (!bedrockResponse.ok) throw new Error(`HTTP ${bedrockResponse.status}`);

      const responseData = await bedrockResponse.json();
      const outputContent = responseData.output.message.content;

      messages.push({ role: "assistant", content: outputContent });
      
      // --- PARALLEL TOOL EXECUTION UPGRADE ---
      const toolUseBlocks = outputContent.filter(block => block.toolUse);
      
      if (toolUseBlocks.length > 0) {
        let toolResultsArr = []; 

        for (const block of toolUseBlocks) {
          const toolName = block.toolUse.name;
          const toolInput = block.toolUse.input;
          let toolResultText = "";

          console.log(`[AGENT EXECUTION] Triggering Tool: ${toolName}`);

          if (toolName === "search_internet") {
            toolResultText = await executeLocalCommand(`node search.js "${toolInput.query}"`);
          } else if (toolName === "create_snapshot") {
            toolResultText = createPreActionSnapshot("AI Autonomous Checkpoint");
          } else if (toolName === "rollback_workspace") {
            toolResultText = rollbackToLastSnapshot();
          } else if (toolName === "map_knowledge") {
            toolResultText = await addGraphEdge(db, toolInput.source, toolInput.relation, toolInput.target);
          } else if (toolName === "query_knowledge") {
            toolResultText = await queryGraph(db, toolInput.entity);
          } else if (toolName === "read_directory") {
            toolResultText = await executeLocalCommand(`dir "${toolInput.path}"`);
          } else if (toolName === "read_file") {
            toolResultText = await executeLocalCommand(`Get-Content -Path "${toolInput.filepath}" -Raw`);
          } else if (toolName === "execute_terminal") {
            const cmdToRun = toolInput.commands[0]; 
            
            const securityCheck = validateCommand(cmdToRun);
            
            if (securityCheck.status === 'BLOCK') {
              toolResultText = `[SECURITY BLOCK] Execution blocked. Reason: ${securityCheck.reason}`;
              console.warn(`[GATEWAY] Blocked autonomous intent: ${cmdToRun}`);
            } else if (securityCheck.status === 'REQUIRE_HUMAN') {
              console.log(`[GATEWAY] Escalating to Human-in-the-Loop: ${cmdToRun}`);
              return res.json({
                type: "tool_use",
                toolUseId: block.toolUse.toolUseId,
                name: toolName,
                input: toolInput,
                text: `[AUTHORIZATION REQUIRED] ${securityCheck.reason}`,
                requiresApproval: true 
              });
            } else {
              toolResultText = await executeLocalCommand(cmdToRun);
            }
          }

          toolResultsArr.push({
            toolResult: {
              toolUseId: block.toolUse.toolUseId,
              content: [{ text: toolResultText || "Success." }]
            }
          });
        }

        messages.push({
          role: "user",
          content: toolResultsArr
        });
        
      } else {
        const textBlock = outputContent.find(block => block.text);
        if (textBlock) {
          const parsedData = extractJSON(textBlock.text);
          isAgentWorking = false; 
          
          if (parsedData) {
            return res.json({ type: "text", ...parsedData });
          } else {
            return res.json({ type: "text", text: textBlock.text.trim(), code: null });
          }
        }
      }
    }
    
    if (loopCount >= MAX_STEPS) {
      return res.json({ type: "text", text: "Agent reached maximum execution steps and paused for safety.", code: null });
    }

  } catch (error) {
    res.status(500).json({ text: "AWS Integration Exception: " + error.message });
  }
});

app.post('/api/terminal', async (req, res) => {
    const { command } = req.body;
    if (!command) return res.json({ output: "No command provided.", isError: true });

    const securityCheck = validateCommand(command);
    
    if (securityCheck.status === 'BLOCK') {
        console.warn(`[SECURITY GATEWAY] Blocked AI Intent: ${command}`);
        return res.json({ output: securityCheck.reason, isError: true, requiresApproval: false });
    }
    
    if (securityCheck.status === 'REQUIRE_HUMAN') {
        console.log(`[SECURITY GATEWAY] Pausing for human approval: ${command}`);
        return res.json({ output: securityCheck.reason, isError: false, requiresApproval: true });
    }

    const shellOptions = process.platform === 'win32' ? { shell: 'powershell.exe' } : {};
    exec(command, { timeout: 30000, maxBuffer: 1024 * 1024 * 10, ...shellOptions }, (error, stdout, stderr) => {
        let combinedOutput = stdout || '';
        if (stderr) combinedOutput += '\n' + stderr;
        if (error) {
            let failOutput = combinedOutput.trim() !== '' ? combinedOutput : error.message;
            return res.json({ output: failOutput, isError: true });
        }
        res.json({ output: (combinedOutput || 'Task completed successfully.').trim(), isError: false });
    });
});

app.post('/api/v1/reflect', async (req, res) => {
  const { command, errorOutput, modelId } = req.body;
  const region = process.env.AWS_REGION || "us-east-1";
  const bearerToken = process.env.AWS_BEARER_TOKEN_BEDROCK?.trim();
  if (!bearerToken) return res.status(500).json({ error: "Missing AWS Token" });

  const reflection = await analyzeAndLogMistake(db, command, errorOutput, modelId, region, bearerToken);
  if (reflection) res.json(reflection);
  else res.status(500).json({ error: "Reflection failed" });
});

app.get('/api/v1/audit/verify', async (req, res) => {
  try {
    const verification = await verifyAuditChain(db);
    res.json(verification);
  } catch (error) {
    res.status(500).json({ error: 'Failed to verify audit chain', details: error.message });
  }
});

const PORT = 5000;
export let db;

initDB().then(async (database) => { 
  db = database;
  await initGraphDB(db); 
  app.listen(PORT, () => console.log(`Agentic Backend streaming on port ${PORT}`));
}).catch(err => {
  console.error("[FATAL] Memory Engine failed:", err);
  process.exit(1);
});