// Minimal ChatKit integration for the AgentKit backend bridge.
//
// The helper keeps the OpenAI thread identifier in localStorage so the
// conversation persists across reloads.

const THREAD_STORAGE_KEY = 'scout-agent-thread-id';

export async function sendAgentMessage(message, sessionId) {
  if (!message || !message.trim()) {
    throw new Error('Message cannot be empty');
  }

  const payload = {
    message: message.trim(),
    session_id: sessionId || null,
    thread_id: localStorage.getItem(THREAD_STORAGE_KEY) || null,
  };

  const response = await fetch('/agent', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || 'Agent request failed');
  }

  const data = await response.json();
  if (data.thread_id) {
    localStorage.setItem(THREAD_STORAGE_KEY, data.thread_id);
  }

  return {
    threadId: data.thread_id,
    table: data.table,
    chart: data.chart,
    sql: data.sql,
    summary: data.summary,
    warnings: data.warnings || [],
  };
}

export function resetAgentThread() {
  localStorage.removeItem(THREAD_STORAGE_KEY);
}
