import { API_BASE, API_HEADERS } from '../config';

async function jsonResponse(response) {
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `Server error ${response.status}`);
  return data;
}

export async function fetchAlignmentEvaluation() {
  const response = await fetch(`${API_BASE}/api/v1/alignment/evaluation`, {
    headers: API_HEADERS,
  });
  return jsonResponse(response);
}

export async function submitAlignmentFeedback(sessionId, feedback) {
  const response = await fetch(`${API_BASE}/api/v1/alignment/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify({ sessionId, ...feedback }),
  });
  return jsonResponse(response);
}
