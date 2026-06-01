import crypto from 'crypto';

export async function analyzeAndLogMistake(db, command, errorOutput, modelId, region, bearerToken) {
  const systemPrompt = `You are a Reflection Agent for an Enterprise AI IDE.
  Your job is to analyze failed terminal commands, extract the root cause, and formulate a generalized lesson so the primary agent does not make this mistake again.
  
  Respond ONLY with a valid JSON object matching this schema:
  {
    "error_type": "Short category (e.g., 'PathNotFound', 'SyntaxError')",
    "root_cause": "Detailed explanation of why it failed",
    "suggested_fix": "How to fix this specific issue",
    "lesson_text": "A generalized rule to avoid this in the future",
    "confidence_delta": -0.1
  }`;

  const prompt = `Command attempted: ${command}\nError Output: ${errorOutput}`;

  try {
    console.log(`[REFLECTION AGENT] Analyzing failed command...`);
    const response = await fetch(`https://bedrock-runtime.${region}.amazonaws.com/model/${modelId}/converse`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${bearerToken}` },
      body: JSON.stringify({
        messages: [{ role: "user", content: [{ text: prompt }] }],
        system: [{ text: systemPrompt }],
        inferenceConfig: { maxTokens: 500, temperature: 0.1 }
      })
    });

    const responseData = await response.json();
    const textContent = responseData.output.message.content.find(b => b.text).text;
    
    // Clean and parse the JSON
    const cleaned = textContent.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
    const parsed = JSON.parse(cleaned);

    const taskId = crypto.randomUUID();

    // Insert into Layer 4 Memory (Mistake Pool)
    const result = await db.run(
      `INSERT INTO mistake_pool (task_id, error_type, root_cause, fix_applied, lesson_text, confidence_delta)
       VALUES (?, ?, ?, ?, ?, ?)`,
      [taskId, parsed.error_type, parsed.root_cause, parsed.suggested_fix, parsed.lesson_text, parsed.confidence_delta || -0.1]
    );

    console.log(`[REFLECTION AGENT] Lesson logged successfully! ID: ${result.lastID}`);
    return { lesson_id: result.lastID, ...parsed, inserted: true };
  } catch (err) {
    console.error("[REFLECTION ERROR] Failed to analyze mistake:", err.message);
    return null;
  }
}