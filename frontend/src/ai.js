import { BedrockRuntimeClient, ConverseCommand } from "@aws-sdk/client-bedrock-runtime";

const client = new BedrockRuntimeClient({
  region: import.meta.env.VITE_AWS_REGION,
  credentials: {
    accessKeyId: import.meta.env.VITE_AWS_ACCESS_KEY_ID,
    secretAccessKey: import.meta.env.VITE_AWS_SECRET_ACCESS_KEY,
  },
});

export const getAIResponse = async (prompt, modelId) => {
  if (!import.meta.env.VITE_AWS_ACCESS_KEY_ID) {
    throw new Error("Missing AWS Credentials in .env file");
  }

  // Strict instructions to force the AI to act as an IDE
  const systemPrompt = `You are an AI code orchestrator embedded in a web-based IDE. 
The user will ask you to build or modify something.
You MUST respond with a valid JSON object. Do NOT wrap it in markdown blockquotes like \`\`\`json.
Your JSON must have three exact keys:
1. "text": A brief message explaining what you did.
2. "code": The raw code. If building a UI, use raw HTML with Tailwind CSS classes. If writing an algorithm, use JavaScript. Do NOT use the phrase "import React" in any generated code.
3. "language": Either "html" or "javascript".`;

  const command = new ConverseCommand({
    modelId: modelId,
    messages: [
      {
        role: "user",
        content: [{ text: prompt }],
      },
    ],
    system: [{ text: systemPrompt }],
    inferenceConfig: { maxTokens: 2000, temperature: 0.4 },
  });

  try {
    const response = await client.send(command);
    const rawText = response.output.message.content[0].text;
    
    // Clean up any accidental markdown the AI might inject
    const cleanedText = rawText.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
    
    return JSON.parse(cleanedText);

  } catch (error) {
    console.error("Bedrock Generation Error:", error);
    return {
      text: `Error connecting to ${modelId}. It might still be provisioning in your AWS region. Check the developer console for details.`,
      code: "// Connection failed.",
      language: "javascript"
    };
  }
};