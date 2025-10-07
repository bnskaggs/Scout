'use client';

import * as React from 'react';
import { ChatKit, useChatKit } from '@openai/chatkit-react';

type ResultPayload = {
  answer?: string;
  chart?: Record<string, unknown>;
  plan?: Record<string, unknown>;
  rowcount?: number;
  runtime_ms?: number;
  sql?: string;
  summary?: string;
  table?: Array<Record<string, unknown>>;
  warnings?: string[];
};

type ChatKitLogEvent = {
  name: string;
  data?: Record<string, unknown>;
  timestamp: number;
};

type ManualChatResponse = {
  answer?: string;
  chart?: Record<string, unknown>;
  plan?: Record<string, unknown>;
  sql?: string;
  summary?: string;
  table?: Array<Record<string, unknown>>;
  warnings?: string[];
};

const CHATKIT_SCRIPT_URL = process.env.NEXT_PUBLIC_CHATKIT_SCRIPT_URL ??
  'https://cdn.openai.com/chatkit/latest/chatkit.js';

function loadChatKitScript(url: string): Promise<void> {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return Promise.resolve();
  }

  if (!url) {
    return Promise.reject(new Error('No ChatKit script URL configured.'));
  }

  const existingElement = document.querySelector<HTMLScriptElement>(
    `script[data-chatkit-src="${url}"]`,
  );

  if (existingElement?.dataset.loaded === 'true') {
    return Promise.resolve();
  }

  return new Promise<void>((resolve, reject) => {
    const script = existingElement ?? document.createElement('script');
    script.async = true;
    script.src = url;
    script.dataset.chatkitSrc = url;

    const handleLoad = () => {
      script.dataset.loaded = 'true';
      resolve();
    };

    const handleError = () => {
      reject(new Error(`Failed to load ChatKit script from ${url}`));
    };

    script.addEventListener('load', handleLoad, { once: true });
    script.addEventListener('error', handleError, { once: true });

    if (!existingElement) {
      document.head.appendChild(script);
    }
  });
}

function useChatKitAvailability() {
  const [status, setStatus] = React.useState<'loading' | 'ready' | 'unavailable'>(() => {
    if (typeof window === 'undefined') {
      return 'loading';
    }
    return window.customElements?.get('openai-chatkit') ? 'ready' : 'loading';
  });
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (typeof window === 'undefined') return;
    let cancelled = false;

    async function ensureChatKit() {
      if (window.customElements?.get('openai-chatkit')) {
        setStatus('ready');
        return;
      }

      try {
        await loadChatKitScript(CHATKIT_SCRIPT_URL);
        await window.customElements.whenDefined('openai-chatkit');
        if (!cancelled) {
          setStatus('ready');
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : 'ChatKit unavailable';
        if (!cancelled) {
          setError(message);
          setStatus('unavailable');
        }
      }
    }

    ensureChatKit();

    return () => {
      cancelled = true;
    };
  }, []);

  return { status, error };
}

function isResultPayload(candidate: unknown): candidate is ResultPayload {
  if (!candidate || typeof candidate !== 'object') {
    return false;
  }
  const value = candidate as Record<string, unknown>;
  return (
    typeof value.summary === 'string' ||
    typeof value.sql === 'string' ||
    Array.isArray(value.table) ||
    Array.isArray(value.warnings)
  );
}

function coercePayload(value: unknown): ResultPayload | null {
  if (value == null) {
    return null;
  }
  if (isResultPayload(value)) {
    return value as ResultPayload;
  }
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      if (isResultPayload(parsed)) {
        return parsed as ResultPayload;
      }
      return coercePayload(parsed);
    } catch {
      return null;
    }
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const result = coercePayload(item);
      if (result) {
        return result;
      }
    }
    return null;
  }
  if (typeof value === 'object') {
    for (const entry of Object.values(value as Record<string, unknown>)) {
      const result = coercePayload(entry);
      if (result) {
        return result;
      }
    }
  }
  return null;
}

function ResultCards({ payload }: { payload: ResultPayload }) {
  if (!payload) return null;
  return (
    <div className="space-y-3">
      {payload.answer && (
        <div className="rounded-2xl border p-3">
          <h3 className="font-semibold">Answer</h3>
          <p>{payload.answer}</p>
        </div>
      )}
      {payload.summary && (
        <div className="rounded-2xl border p-3">
          <h3 className="font-semibold">Summary</h3>
          <p>{payload.summary}</p>
        </div>
      )}
      {payload.sql && (
        <div className="rounded-2xl border p-3">
          <h3 className="font-semibold">SQL</h3>
          <pre className="whitespace-pre-wrap text-xs">{payload.sql}</pre>
        </div>
      )}
      {Array.isArray(payload.table) && payload.table.length > 0 && (
        <div className="rounded-2xl border p-3 overflow-x-auto">
          <h3 className="font-semibold mb-2">Table</h3>
          <table className="text-sm">
            <thead>
              <tr>
                {Object.keys(payload.table[0]).map((k) => (
                  <th key={k} className="px-2 py-1 text-left">
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {payload.table.map((row, i) => (
                <tr key={i}>
                  {Object.keys(payload.table![0]).map((k) => (
                    <td key={k} className="px-2 py-1">
                      {String(row[k] ?? '')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {/* Placeholder chart card for Phase 0; wire Recharts later */}
      {payload.chart && (
        <div className="rounded-2xl border p-3">
          <h3 className="font-semibold">Chart</h3>
          <pre className="text-xs">{JSON.stringify(payload.chart, null, 2)}</pre>
        </div>
      )}
      {!!(payload.warnings?.length) && (
        <div className="rounded-2xl border p-3 bg-yellow-50">
          <h3 className="font-semibold">Warnings</h3>
          <ul className="list-disc ml-4">
            {payload.warnings!.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function FallbackChatPanel({ reason }: { reason: string }) {
  const [question, setQuestion] = React.useState('');
  const [contextEnabled, setContextEnabled] = React.useState(true);
  const [pendingClarification, setPendingClarification] = React.useState<{
    question: string;
    options: string[];
  } | null>(null);
  const [result, setResult] = React.useState<ResultPayload | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [history, setHistory] = React.useState<string[]>([]);
  const sessionIdRef = React.useRef<string>('');
  if (!sessionIdRef.current) {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      sessionIdRef.current = crypto.randomUUID();
    } else {
      sessionIdRef.current = `session-${Math.random().toString(36).slice(2)}`;
    }
  }

  const persistHistory = React.useCallback((entry: string) => {
    setHistory((prev) => {
      const next = [entry, ...prev.filter((item) => item !== entry)];
      return next.slice(0, 8);
    });
  }, []);

  const coerceManualPayload = React.useCallback((data: ManualChatResponse | null | undefined): ResultPayload | null => {
    if (!data) return null;
    return {
      answer: typeof data.answer === 'string' ? data.answer : undefined,
      summary: typeof data.summary === 'string' ? data.summary : undefined,
      sql: typeof data.sql === 'string' ? data.sql : undefined,
      chart: typeof data.chart === 'object' ? data.chart ?? undefined : undefined,
      plan: typeof data.plan === 'object' ? data.plan ?? undefined : undefined,
      table: Array.isArray(data.table) ? data.table : undefined,
      warnings: Array.isArray(data.warnings) ? data.warnings : undefined,
    } satisfies ResultPayload;
  }, []);

  const submit = React.useCallback(
    async (utterance: string, clarificationAnswer?: string) => {
      const trimmed = utterance.trim();
      if (!trimmed) {
        setError('Please enter a question.');
        return;
      }
      setError(null);
      setLoading(true);
      try {
        const res = await fetch('/api/manual-chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sessionId: sessionIdRef.current,
            question: clarificationAnswer ? undefined : trimmed,
            clarification: clarificationAnswer ?? null,
            contextEnabled,
          }),
        });

        if (!res.ok) {
          const detail = await res.json().catch(() => ({}));
          const message = detail?.error || detail?.detail || res.statusText || 'Request failed';
          throw new Error(message);
        }

        const payload = (await res.json()) as {
          status?: string;
          data?: ManualChatResponse;
          clarification?: {
            question: string;
            suggested_answers?: string[];
          };
        };

        if (payload.status === 'clarification_needed' && payload.clarification) {
          setPendingClarification({
            question: payload.clarification.question,
            options: payload.clarification.suggested_answers ?? [],
          });
          setResult(null);
        } else if (payload.data) {
          setPendingClarification(null);
          const coerced = coerceManualPayload(payload.data);
          setResult(coerced);
          if (!clarificationAnswer) {
            persistHistory(trimmed);
          }
          setQuestion('');
        } else {
          throw new Error('Unexpected response from the backend');
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Something went wrong';
        setError(message);
      } finally {
        setLoading(false);
      }
    },
    [contextEnabled, coerceManualPayload, persistHistory],
  );

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-dashed bg-orange-50 p-4 text-sm text-orange-900">
        <p className="font-semibold">Chat interface fallback</p>
        <p>
          The ChatKit widget could not be loaded ({reason}). You can continue by using the lightweight
          text interface below. Configure <code>NEXT_PUBLIC_CHATKIT_SCRIPT_URL</code> to re-enable the full
          chat experience.
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-4">
          <div className="rounded-2xl border p-4">
            <label className="block text-sm font-medium" htmlFor="fallback-question">
              Ask a question
            </label>
            <textarea
              id="fallback-question"
              className="mt-2 h-32 w-full resize-y rounded-lg border p-2 text-sm focus:border-blue-500 focus:outline-none"
              placeholder="e.g. How many incidents were reported last month?"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              disabled={loading}
            />
            <div className="mt-3 flex items-center justify-between gap-3">
              <button
                type="button"
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:bg-blue-300"
                onClick={() => submit(question, pendingClarification ? question : undefined)}
                disabled={loading}
              >
                {loading ? 'Submitting…' : 'Run analysis'}
              </button>
              <label className="flex items-center gap-2 text-xs text-neutral-600">
                <input
                  type="checkbox"
                  checked={contextEnabled}
                  onChange={(event) => setContextEnabled(event.target.checked)}
                />
                Keep conversation context
              </label>
            </div>
            {error ? (
              <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-2 text-sm text-red-700">
                {error}
              </div>
            ) : null}
            {pendingClarification ? (
              <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <p className="font-semibold">Clarification needed</p>
                <p className="mt-1">{pendingClarification.question}</p>
                <p className="mt-1 text-xs text-amber-800">
                  Choose one of the suggestions below or type your own answer above and run it again.
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {pendingClarification.options.map((option) => (
                    <button
                      key={option}
                      type="button"
                      className="rounded-full border border-amber-400 px-3 py-1 text-xs"
                      onClick={() => {
                        setQuestion(option);
                        submit(option, option);
                      }}
                      disabled={loading}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
          {history.length > 0 ? (
            <div className="rounded-2xl border p-4">
              <h3 className="text-sm font-semibold">Recent questions</h3>
              <ul className="mt-2 space-y-1 text-xs text-neutral-600">
                {history.map((item) => (
                  <li key={item}>
                    <button
                      type="button"
                      className="hover:text-neutral-900"
                      onClick={() => {
                        setQuestion(item);
                        submit(item);
                      }}
                    >
                      {item}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
        <div className="rounded-2xl border p-4">
          <h2 className="mb-2 font-semibold">Results</h2>
          {result ? (
            <ResultCards payload={result} />
          ) : (
            <p className="text-sm text-neutral-500">Submit a question to see results.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function ChatKitPanel() {
  const [threadId, setThreadId] = React.useState<string | null>(() => {
    return typeof window !== 'undefined' ? localStorage.getItem('truesight_thread_id') : null;
  });
  const [logEvents, setLogEvents] = React.useState<ChatKitLogEvent[]>([]);

  const handleThreadChange = React.useCallback((detail: { threadId: string | null }) => {
    const nextId = detail.threadId ?? null;
    if (typeof window !== 'undefined') {
      if (nextId) {
        localStorage.setItem('truesight_thread_id', nextId);
      } else {
        localStorage.removeItem('truesight_thread_id');
      }
    }
    setThreadId(nextId);
    setLogEvents([]);
  }, []);

  const handleLog = React.useCallback((detail: { name: string; data?: Record<string, unknown> }) => {
    setLogEvents((prev) => {
      const next: ChatKitLogEvent[] = [...prev, { ...detail, timestamp: Date.now() }];
      return next.slice(-200);
    });
  }, []);

  const { control } = useChatKit({
    api: {
      async getClientSecret() {
        const res = await fetch('/api/chatkit/session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ thread_id: threadId ?? undefined }),
        });
        if (!res.ok) {
          throw new Error('Failed to obtain ChatKit client secret');
        }
        const { client_secret, thread_id } = (await res.json()) as {
          client_secret: string;
          thread_id?: string;
        };
        if (thread_id && typeof window !== 'undefined') {
          localStorage.setItem('truesight_thread_id', thread_id);
          setThreadId(thread_id);
        }
        return client_secret;
      },
    },
    initialThread: threadId ?? undefined,
    onThreadChange: handleThreadChange,
    onLog: handleLog,
  });

  const latestPayload = React.useMemo<ResultPayload | null>(() => {
    for (let i = logEvents.length - 1; i >= 0; i -= 1) {
      const entry = logEvents[i];
      const payload = coercePayload(entry?.data ?? entry);
      if (payload) {
        return payload;
      }
    }
    return null;
  }, [logEvents]);

  const recentToolEvents = React.useMemo(() => {
    const matches = logEvents.filter((event) => {
      const name = event.name?.toLowerCase?.() ?? '';
      const dataName = typeof event.data?.name === 'string' ? event.data.name.toLowerCase() : '';
      const eventType = typeof event.data?.event === 'string' ? event.data.event.toLowerCase() : '';
      return name.includes('tool') || dataName.includes('tool') || eventType.includes('tool');
    });
    const source = matches.length > 0 ? matches : logEvents;
    return source.slice(-8).reverse();
  }, [logEvents]);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="rounded-2xl border">
        <ChatKit control={control} className="h-[640px] w-full" />
      </div>
      <div className="rounded-2xl border p-3">
        <h2 className="mb-2 font-semibold">Results</h2>
        {latestPayload ? (
          <ResultCards payload={latestPayload} />
        ) : (
          <p className="text-sm text-neutral-500">Ask a question to see results.</p>
        )}
        <div className="mt-4 border-t pt-3">
          <h3 className="mb-2 text-sm font-semibold">Tool activity</h3>
          {recentToolEvents.length > 0 ? (
            <ul className="space-y-1 text-xs text-neutral-600">
              {recentToolEvents.map((event) => {
                const key = `${event.timestamp}-${event.name}`;
                const summary = event.data?.name || event.data?.event;
                return (
                  <li key={key} className="flex items-start gap-2">
                    <span className="mt-[2px] h-1.5 w-1.5 flex-none rounded-full bg-emerald-400" aria-hidden />
                    <div>
                      <span className="font-medium text-neutral-700">{event.name}</span>
                      {summary ? <span className="ml-1 text-neutral-500">{String(summary)}</span> : null}
                      {event.data && !summary ? (
                        <pre className="mt-1 whitespace-pre-wrap text-[10px] text-neutral-500">
                          {JSON.stringify(event.data, null, 2)}
                        </pre>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-xs text-neutral-400">Waiting for tool calls…</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ChatPanel() {
  const { status, error } = useChatKitAvailability();

  if (status === 'loading') {
    return (
      <div className="rounded-2xl border p-6 text-sm text-neutral-600">
        Preparing chat interface…
      </div>
    );
  }

  if (status === 'unavailable') {
    return <FallbackChatPanel reason={error ?? 'ChatKit unavailable'} />;
  }

  return <ChatKitPanel />;
}
