import { API_BASE, API_HEADERS } from '../config';

function textOf(message) {
  const content = message?.content;
  if (typeof content === 'string') return content;
  if (!Array.isArray(content)) return '';
  return content
    .filter(item => item && typeof item.text === 'string')
    .map(item => item.text)
    .join(' ')
    .trim();
}

export async function restoreConversationSession(sessionId) {
  const response = await fetch(`${API_BASE}/api/v1/conversation/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify({ sessionId, limit: 50 }),
  });
  if (!response.ok) throw new Error(`Server error ${response.status}`);

  const data = await response.json();
  const history = Array.isArray(data.messages)
    ? data.messages.filter(message => ['user', 'assistant'].includes(message?.role) && textOf(message))
    : [];
  const messages = history.map((message, index) => ({
    id: `restored-${index}`,
    sender: message.role === 'assistant' ? 'ai' : 'user',
    text: textOf(message),
    steps: [],
    settled: true,
  }));
  return {
    alignment: data.alignment && typeof data.alignment === 'object' ? data.alignment : null,
    activeCorrection: data.activeCorrection && typeof data.activeCorrection === 'object'
      ? data.activeCorrection
      : null,
    correctionHistory: Array.isArray(data.correctionHistory) ? data.correctionHistory : [],
    history,
    messages,
  };
}

async function correctionRequest(path, sessionId, corrections) {
  const body = corrections === undefined ? { sessionId } : { sessionId, corrections };
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `Server error ${response.status}`);
  return {
    alignment: data.alignment && typeof data.alignment === 'object' ? data.alignment : null,
    activeCorrection: data.activeCorrection && typeof data.activeCorrection === 'object'
      ? data.activeCorrection
      : null,
    correctionHistory: Array.isArray(data.correctionHistory) ? data.correctionHistory : [],
  };
}

export function correctConversationAlignment(sessionId, corrections) {
  return correctionRequest('/api/v1/conversation/correction', sessionId, corrections);
}

export function clearConversationCorrection(sessionId) {
  return correctionRequest('/api/v1/conversation/correction/clear', sessionId);
}
