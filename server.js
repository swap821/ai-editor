import 'dotenv/config'; 
import express from 'express';
import cors from 'cors';
import { exec } from 'child_process';
import { initDB } from './database.js';
import { logAuditEntry, verifyAuditChain } from './auditLogger.js';
import { analyzeAndLogMistake } from './reflectionEngine.js';
import { hybridMemorySearch } from './memoryAgent.js';
import { scanAndRedactSecrets } from './secretScanner.js';
import { validateCommand, classify, Zone } from './securityGateway.js';
import { filterSteps } from './confidenceFilter.js';
import { createPreActionSnapshot, rollbackToLastSnapshot } from './rollbackEngine.js';
import { initGraphDB, addGraphEdge, queryGraph } from './knowledgeGraph.js';
import { converseLLM, isLocalModel, listOllamaModels } from './llmProvider.js';

const app = express();
app.use(cors());
app.use(express.json());

const SESSION_ID = "session-alpha";

// Log an action to the tamper-evident audit chain, redacting any secrets first.
// Audit failures are non-fatal to the request but always surfaced in logs.
async function auditAction(actor, payload, zone = 'YELLOW') {
  try {
    const { scrubbedPayload } = scanAndRedactSecrets(String(payload ?? ''));
    await logAuditEntry(db, actor, scrubbedPayload, zone);
  } catch (e) {
    console.error('[AUDIT] Failed to record action:', e.message);
  }
}

// Fire-and-forget reflection: analyse a failed command and store a lesson.
// Works for both local (Ollama) and cloud (Bedrock) models — cloud additionally
// requires a bearer token; local needs only the model id.
function reflectOnFailure(command, errorOutput, modelId) {
  if (!modelId) return;
  const region = process.env.AWS_REGION || "us-east-1";
  const bearerToken = process.env.AWS_BEARER_TOKEN_BEDROCK?.trim();
  if (!isLocalModel(modelId) && !bearerToken) return;
  analyzeAndLogMistake(db, command, errorOutput, modelId, region, bearerToken)
    .then(r => { if (r) console.log(`[REFLECTION] Lesson #${r.lesson_id} stored from failure.`); })
    .catch(e => console.error('[REFLECTION] background failure:', e.message));
}

// Cheap heuristic to detect a failed terminal result so we can auto-reflect.
function looksLikeFailure(output) {
  if (!output) return false;
  return /\b(error|exception|not recognized|cannot find|fatal|denied|failed|traceback)\b/i.test(output);
}

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

  // Cloud (Bedrock) models need a bearer token; local (Ollama) models do not.
  if (!isLocalModel(modelId) && !bearerToken) {
    return res.status(500).json({ text: "AWS Error: Missing API Key (or pick a Local model)." });
  }

  // SSE streaming setup
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.flushHeaders();

  const emit = (event, data) => {
    if (!res.writableEnded) {
      res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
    }
  };

  if (!messages || !Array.isArray(messages) || messages.length === 0) {
    emit('error', { text: "No messages provided." });
    return res.end();
  }

  let latestQuery = "";
  const lastMsg = messages[messages.length - 1];
  if (lastMsg.role === "user" && lastMsg.content?.[0]?.text) {
    latestQuery = lastMsg.content[0].text;
    await db.run(
      `INSERT INTO episodic_memory (session_id, role, content) VALUES (?, ?, ?)`,
      [SESSION_ID, "user", latestQuery]
    ).catch(() => {});
  }

  const recalledMemories = await hybridMemorySearch(db, latestQuery, 3);
  let memoryContextBlock = "";
  if (recalledMemories.length > 0) {
    memoryContextBlock = "\n--- AUTHORITATIVE PROJECT KNOWLEDGE BASE ---\n";
    recalledMemories.forEach(m => { memoryContextBlock += `${m.content}\n\n`; });
    memoryContextBlock += "--------------------------------------------\n";
  }

  const systemPrompt = `You are an elite, fully autonomous Agentic AI integrated directly into an IDE workspace.
${memoryContextBlock}
CRITICAL KNOWLEDGE DIRECTIVE:
If the user asks a question about the project architecture, specifications, or blueprints, YOU MUST base your answer strictly on the 'AUTHORITATIVE PROJECT KNOWLEDGE BASE' provided above. Do not hallucinate or use generalized industry knowledge.

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

    const conversationMessages = [...messages];

    while (isAgentWorking && loopCount < MAX_STEPS) {
      loopCount++;
      console.log(`[AGENT LOOP] Iteration ${loopCount}...`);

      const responseData = await converseLLM({
        modelId,
        messages: conversationMessages,
        system: systemBlock,
        toolConfig: { tools: workspaceTools },
        inferenceConfig: { maxTokens: 2000, temperature: 0.3 },
        region,
        bearerToken,
      });

      const outputContent = responseData.output.message.content;

      conversationMessages.push({ role: "assistant", content: outputContent });

      const toolUseBlocks = outputContent.filter(block => block.toolUse);

      if (toolUseBlocks.length > 0) {
        const toolResultsArr = [];

        for (const block of toolUseBlocks) {
          const toolName = block.toolUse.name;
          const toolInput = block.toolUse.input;
          const toolUseId = block.toolUse.toolUseId;
          let toolResultText = "";

          console.log(`[AGENT EXECUTION] Triggering Tool: ${toolName}`);
          emit('step', { type: 'tool_call', tool: toolName, input: toolInput, id: toolUseId });

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
            const securityCheck = validateCommand(cmdToRun, { sessionId: SESSION_ID });

            if (securityCheck.status === 'BLOCK') {
              toolResultText = `[SECURITY BLOCK] Execution blocked. Reason: ${securityCheck.reason}`;
              emit('step', { type: 'tool_blocked', tool: toolName, reason: securityCheck.reason, id: toolUseId });
              console.warn(`[GATEWAY] Blocked autonomous intent: ${cmdToRun}`);
              await auditAction('agent', `BLOCKED: ${cmdToRun}`, Zone.RED);
            } else if (securityCheck.status === 'REQUIRE_HUMAN') {
              console.log(`[GATEWAY] Escalating to Human-in-the-Loop: ${cmdToRun}`);
              await auditAction('agent', `ESCALATED: ${cmdToRun}`, Zone.YELLOW);
              emit('human_required', {
                toolUseId,
                name: toolName,
                input: toolInput,
                text: `[AUTHORIZATION REQUIRED] ${securityCheck.reason}`,
                requiresApproval: true
              });
              return res.end();
            } else {
              await auditAction('agent', `EXECUTED: ${cmdToRun}`, Zone.GREEN);
              toolResultText = await executeLocalCommand(cmdToRun);
              if (looksLikeFailure(toolResultText)) reflectOnFailure(cmdToRun, toolResultText, modelId);
            }
          }

          if (!toolResultText) toolResultText = "Success.";
          emit('step', { type: 'tool_result', tool: toolName, output: String(toolResultText).slice(0, 400), id: toolUseId });

          toolResultsArr.push({
            toolResult: {
              toolUseId,
              content: [{ text: toolResultText }]
            }
          });
        }

        conversationMessages.push({ role: "user", content: toolResultsArr });

      } else {
        const textBlock = outputContent.find(block => block.text);
        if (textBlock) {
          isAgentWorking = false;
          const parsedData = extractJSON(textBlock.text);

          if (parsedData?.code) {
            emit('code', { code: parsedData.code, language: parsedData.language || 'javascript' });
            const words = (parsedData.text || "Code updated.").split(/(\s+)/);
            for (const chunk of words) {
              emit('text_chunk', { text: chunk });
              if (chunk.trim()) await new Promise(r => setTimeout(r, 18));
            }
          } else {
            const words = textBlock.text.trim().split(/(\s+)/);
            for (const chunk of words) {
              emit('text_chunk', { text: chunk });
              if (chunk.trim()) await new Promise(r => setTimeout(r, 18));
            }
          }
          emit('done', {});
        }
      }
    }

    if (loopCount >= MAX_STEPS) {
      emit('text_chunk', { text: "Agent reached maximum execution steps and paused for safety." });
      emit('done', {});
    }

  } catch (error) {
    const where = isLocalModel(modelId) ? 'Local inference error' : 'Cloud inference error';
    emit('error', { text: `${where}: ${error.message}` });
  }

  res.end();
});

app.post('/api/terminal', async (req, res) => {
    const { command, modelId } = req.body;
    if (!command) return res.json({ output: "No command provided.", isError: true });

    const securityCheck = validateCommand(command, { sessionId: SESSION_ID });

    if (securityCheck.status === 'BLOCK') {
        console.warn(`[SECURITY GATEWAY] Blocked AI Intent: ${command}`);
        await auditAction('human-terminal', `BLOCKED: ${command}`, Zone.RED);
        return res.json({ output: securityCheck.reason, isError: true, requiresApproval: false });
    }

    if (securityCheck.status === 'REQUIRE_HUMAN') {
        console.log(`[SECURITY GATEWAY] Pausing for human approval: ${command}`);
        await auditAction('human-terminal', `ESCALATED: ${command}`, Zone.YELLOW);
        return res.json({ output: securityCheck.reason, isError: false, requiresApproval: true });
    }

    await auditAction('human-terminal', `EXECUTED: ${command}`, Zone.GREEN);

    const shellOptions = process.platform === 'win32' ? { shell: 'powershell.exe' } : {};
    exec(command, { timeout: 30000, maxBuffer: 1024 * 1024 * 10, ...shellOptions }, (error, stdout, stderr) => {
        let combinedOutput = stdout || '';
        if (stderr) combinedOutput += '\n' + stderr;
        if (error) {
            let failOutput = combinedOutput.trim() !== '' ? combinedOutput : error.message;
            reflectOnFailure(command, failOutput, modelId);
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

// Deterministic security classification (blueprint /api/v1/security/classify).
app.post('/api/v1/security/classify', (req, res) => {
  const { action } = req.body || {};
  if (typeof action !== 'string') {
    return res.status(400).json({ error: 'Body must include { action: string }.' });
  }
  const result = classify(action);
  res.json(result);
});

// Hybrid memory search (blueprint /api/v1/memory/search).
app.post('/api/v1/memory/search', async (req, res) => {
  const { query, top_k } = req.body || {};
  if (typeof query !== 'string' || !query.trim()) {
    return res.status(400).json({ error: 'Body must include { query: string }.' });
  }
  try {
    const results = await hybridMemorySearch(db, query, top_k || 3);
    res.json({ results, scores: results.map(r => r.score ?? null) });
  } catch (e) {
    res.status(503).json({ error: 'Memory search unavailable', details: e.message });
  }
});

// Local model discovery: lists models installed in the local Ollama engine so
// the UI can show what is actually runnable offline (and whether Ollama is up).
app.get('/api/v1/models/local', async (req, res) => {
  const status = await listOllamaModels();
  res.json(status);
});

// Planner + confidence filter (blueprint /api/v1/plan).
// Decomposes a goal into steps WITH per-step confidence, then gates each step
// at the 0.72 threshold. Steps below threshold are escalated to human review.
app.post('/api/v1/plan', async (req, res) => {
  const { goal, modelId } = req.body || {};
  const region = process.env.AWS_REGION || "us-east-1";
  const bearerToken = process.env.AWS_BEARER_TOKEN_BEDROCK?.trim();
  if (typeof goal !== 'string' || !goal.trim()) {
    return res.status(400).json({ error: 'Body must include { goal: string }.' });
  }
  if (!modelId) {
    return res.status(500).json({ error: 'Missing modelId.' });
  }
  if (!isLocalModel(modelId) && !bearerToken) {
    return res.status(500).json({ error: 'Missing AWS token (or use a Local model).' });
  }

  const systemPrompt = `You are a software planning agent. Decompose the user's goal into 3-6 concrete, ordered sub-tasks.
For each sub-task estimate your confidence (0.0-1.0) that you can complete it correctly without human help.
Respond ONLY with valid JSON: { "steps": [ { "step_id": "1", "description": "...", "confidence": 0.0 } ] }`;

  try {
    const data = await converseLLM({
      modelId,
      messages: [{ role: "user", content: [{ text: `Goal: ${goal}` }] }],
      system: [{ text: systemPrompt }],
      inferenceConfig: { maxTokens: 800, temperature: 0.2 },
      region,
      bearerToken,
    });
    const text = data.output.message.content.find(b => b.text).text;
    const parsed = extractJSON(text);
    const steps = (parsed && Array.isArray(parsed.steps)) ? parsed.steps : [];
    const { approved, escalate } = filterSteps(steps);
    res.json({ goal, task_tree: steps, approved, escalate });
  } catch (error) {
    res.status(500).json({ error: 'Planning failed', details: error.message });
  }
});

const PORT = process.env.PORT || 5000;
export let db;

initDB().then(async (database) => { 
  db = database;
  await initGraphDB(db); 
  app.listen(PORT, () => console.log(`Agentic Backend streaming on port ${PORT}`));
}).catch(err => {
  console.error("[FATAL] Memory Engine failed:", err);
  process.exit(1);
});