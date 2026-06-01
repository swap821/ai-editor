// llmProvider.js
// Unified LLM gateway that abstracts the inference backend behind a single
// Bedrock-shaped contract. The rest of the server speaks ONE format
// (Amazon Bedrock Converse); this module translates to/from a local Ollama
// engine when a local model is selected.
//
// Why a single shape: server.js's agentic loop is built around the Bedrock
// Converse response (`output.message.content[]` with `text` / `toolUse`
// blocks, `toolResult` for tool returns). Keeping that as the canonical
// shape means the loop, the planner, and the reflection engine need ZERO
// awareness of which engine actually ran — flipping local<->cloud is just a
// model id.
//
// Routing rule: a modelId beginning with "ollama." runs locally; anything
// else runs on Bedrock. This makes the project "local-first" per the blueprint
// (all inference offline) the moment a local model is chosen.

import crypto from 'crypto';

const OLLAMA_HOST = (process.env.OLLAMA_HOST || 'http://localhost:11434').replace(/\/$/, '');

/** True when the model should run on the local Ollama engine. */
export function isLocalModel(modelId) {
  return typeof modelId === 'string' && modelId.startsWith('ollama.');
}

/** Strip the routing prefix to recover the real Ollama tag (ollama.llama3.2 -> llama3.2). */
function ollamaTag(modelId) {
  return modelId.replace(/^ollama\./, '');
}

/* ─── Bedrock path (unchanged behaviour) ─────────────────────────────────── */
async function bedrockConverse({ modelId, messages, system, toolConfig, inferenceConfig, region, bearerToken }) {
  const res = await fetch(`https://bedrock-runtime.${region}.amazonaws.com/model/${modelId}/converse`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${bearerToken}` },
    body: JSON.stringify({
      messages,
      system,
      ...(toolConfig ? { toolConfig } : {}),
      inferenceConfig,
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Bedrock HTTP ${res.status}${detail ? `: ${detail.slice(0, 200)}` : ''}`);
  }
  return res.json();
}

/* ─── Bedrock → Ollama translation ───────────────────────────────────────── */

// Bedrock `system` is an array of blocks (text + cachePoint); Ollama wants one
// system string. Drop non-text blocks (e.g. cachePoint — not applicable locally).
function systemToText(system) {
  if (!system) return '';
  if (typeof system === 'string') return system;
  return system.filter(b => b && b.text).map(b => b.text).join('\n');
}

// Convert the canonical Bedrock message history into Ollama /api/chat messages.
// - text blocks      -> message.content string
// - toolUse blocks   -> message.tool_calls[]
// - toolResult blocks -> separate { role: 'tool', content } messages (Ollama
//   matches tool results to calls by order, so the ids are not needed here).
function messagesToOllama(messages) {
  const out = [];
  for (const msg of messages) {
    const content = msg.content;
    if (typeof content === 'string') {
      out.push({ role: msg.role, content });
      continue;
    }
    const textParts = [];
    const toolCalls = [];
    const toolResults = [];
    for (const block of content || []) {
      if (block.text) {
        textParts.push(block.text);
      } else if (block.toolUse) {
        toolCalls.push({
          function: { name: block.toolUse.name, arguments: block.toolUse.input || {} },
        });
      } else if (block.toolResult) {
        const t = (block.toolResult.content || []).filter(c => c.text).map(c => c.text).join('\n');
        toolResults.push(t);
      }
    }
    if (toolResults.length > 0) {
      for (const t of toolResults) out.push({ role: 'tool', content: t });
    } else {
      const m = { role: msg.role, content: textParts.join('\n') };
      if (toolCalls.length > 0) m.tool_calls = toolCalls;
      out.push(m);
    }
  }
  return out;
}

// Bedrock toolSpec -> Ollama (OpenAI-style) function tool.
function toolsToOllama(toolConfig) {
  if (!toolConfig || !Array.isArray(toolConfig.tools)) return undefined;
  return toolConfig.tools.map(t => ({
    type: 'function',
    function: {
      name: t.toolSpec.name,
      description: t.toolSpec.description,
      parameters: t.toolSpec.inputSchema?.json || { type: 'object', properties: {} },
    },
  }));
}

function safeParse(s) {
  if (typeof s !== 'string') return s || {};
  try { return JSON.parse(s); } catch { return {}; }
}

// Ollama /api/chat response -> canonical Bedrock Converse shape.
function ollamaToBedrock(data) {
  const msg = data.message || {};
  const content = [];
  if (msg.content && msg.content.trim()) content.push({ text: msg.content });
  if (Array.isArray(msg.tool_calls)) {
    for (const tc of msg.tool_calls) {
      content.push({
        toolUse: {
          toolUseId: crypto.randomUUID(),
          name: tc.function?.name,
          input: safeParse(tc.function?.arguments),
        },
      });
    }
  }
  if (content.length === 0) content.push({ text: '' });
  return {
    output: { message: { role: 'assistant', content } },
    stopReason: data.done_reason || 'end_turn',
  };
}

/* ─── Ollama path ────────────────────────────────────────────────────────── */
async function ollamaConverse({ modelId, messages, system, toolConfig, inferenceConfig }) {
  const ollamaMessages = [];
  const sys = systemToText(system);
  if (sys) ollamaMessages.push({ role: 'system', content: sys });
  ollamaMessages.push(...messagesToOllama(messages));

  const body = {
    model: ollamaTag(modelId),
    messages: ollamaMessages,
    stream: false,
    options: {
      temperature: inferenceConfig?.temperature ?? 0.3,
      num_predict: inferenceConfig?.maxTokens ?? 2000,
    },
  };
  const tools = toolsToOllama(toolConfig);
  if (tools) body.tools = tools;

  let res;
  try {
    res = await fetch(`${OLLAMA_HOST}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (e) {
    throw new Error(`Ollama unreachable at ${OLLAMA_HOST} — is it running? (${e.message})`);
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Ollama HTTP ${res.status}${detail ? `: ${detail.slice(0, 200)}` : ''}`);
  }
  return ollamaToBedrock(await res.json());
}

/* ─── Unified entry point ────────────────────────────────────────────────── */
// Always returns a Bedrock-shaped response: { output: { message: { content[] } } }.
export async function converseLLM({ modelId, messages, system, toolConfig, inferenceConfig, region, bearerToken }) {
  if (isLocalModel(modelId)) {
    return ollamaConverse({ modelId, messages, system, toolConfig, inferenceConfig });
  }
  return bedrockConverse({ modelId, messages, system, toolConfig, inferenceConfig, region, bearerToken });
}

/** List the models actually installed in the local Ollama engine (for the UI). */
export async function listOllamaModels() {
  try {
    const res = await fetch(`${OLLAMA_HOST}/api/tags`);
    if (!res.ok) return { available: false, models: [] };
    const data = await res.json();
    return { available: true, models: (data.models || []).map(m => m.name) };
  } catch {
    return { available: false, models: [] };
  }
}
