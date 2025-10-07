'use client';

import * as React from 'react';
import { ChatKit, useChatKit } from '@openai/chatkit-react';

type ResultPayload = {
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

export default function ChatPanel() {
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
