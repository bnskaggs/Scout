"use client";

import { ChatKit, useChatKit } from "@openai/chatkit-react";
import { useEffect, useMemo, useState } from "react";
import InsightPanel, { InsightPanelData } from "./components/InsightPanel";

type MessageContentBlock = {
  type?: string;
  name?: string;
  text?: string;
  data?: unknown;
};

type ChatKitMessage = {
  content?: MessageContentBlock[];
  metadata?: Record<string, any> | null;
  role?: string;
};

export default function ChatPage() {
  const [insight, setInsight] = useState<InsightPanelData | null>(null);
  const [sessionId] = useState(() => `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);

  const { control, error, messages } = useChatKit({
    api: {
      async getClientSecret(_existing) {
        const res = await fetch("/api/chatkit/session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        const { client_secret, error } = await res.json();
        if (error) throw new Error(error);
        return client_secret;
      },
    },
  });

  const chatMessages = useMemo(() => (Array.isArray(messages) ? (messages as ChatKitMessage[]) : []), [messages]);

  useEffect(() => {
    if (!chatMessages.length) return;
    const latest = chatMessages[chatMessages.length - 1];
    const contentBlocks = Array.isArray(latest?.content) ? latest.content : [];

    // DEBUG: Log the message structure
    console.log('[ChatKit Debug] Latest message:', {
      role: latest?.role,
      contentBlocks: contentBlocks,
      metadata: latest?.metadata,
      fullMessage: latest
    });

    if ((latest?.role && latest.role !== "assistant") || (contentBlocks.length === 0 && !latest?.metadata)) {
      return;
    }

    const chartBlock = contentBlocks.find((block) => block?.name === "chart");
    const tableBlock = contentBlocks.find((block) => block?.name === "table");
    const textBlock = contentBlocks.find((block) => typeof block?.text === "string");
    const followupsBlock = contentBlocks.find((block) => block?.name === "followups");

    const chartData =
      chartBlock && typeof chartBlock === "object" && chartBlock.data && typeof chartBlock.data === "object"
        ? (chartBlock.data as InsightPanelData["chart"])
        : null;
    const tableData =
      tableBlock && typeof tableBlock === "object" && Array.isArray(tableBlock.data as unknown[])
        ? (tableBlock.data as InsightPanelData["table"])
        : null;
    const followupsData =
      followupsBlock && followupsBlock.data && typeof followupsBlock.data === "object" &&
      Array.isArray((followupsBlock.data as any)?.suggestions)
        ? ((followupsBlock.data as any).suggestions as string[])
        : null;

    const metadata = latest?.metadata ?? {};
    const warnings = Array.isArray(metadata?.warnings) ? metadata.warnings : [];
    const summaryText =
      typeof textBlock?.text === "string"
        ? textBlock.text
        : typeof metadata?.answer === "string"
          ? metadata.answer
          : "";
    const chartFromMetadata = metadata?.chart && typeof metadata.chart === "object" ? metadata.chart : null;
    const tableFromMetadata = Array.isArray(metadata?.table) ? metadata.table : null;

    const resolvedChart = (chartData as InsightPanelData["chart"]) ?? (chartFromMetadata as InsightPanelData["chart"]) ?? null;
    const resolvedTable = (tableData as InsightPanelData["table"]) ?? (tableFromMetadata as InsightPanelData["table"]) ?? null;

    const insightPayload: InsightPanelData = {
      summary: summaryText,
      chart: resolvedChart,
      table: resolvedTable,
      sql: metadata?.sql ?? null,
      plan: metadata?.plan ?? null,
      lineage: metadata?.lineage ?? null,
      warnings,
      status: metadata?.status ?? null,
      followups: followupsData,
      chips: metadata?.chips ?? null,
      nqlStatus: metadata?.nql_status ?? null,
    };

    setInsight(insightPayload);

    // WORKAROUND: Try to fetch cached data if no table/chart found
    if (!resolvedTable && !resolvedChart && latest?.role === 'assistant') {
      console.log('[ChatKit] No structured data in message, fetching from cache...');
      fetch(`/api/tools/truesight-query?session_id=${sessionId}`)
        .then(res => res.json())
        .then(cached => {
          if (cached.table || cached.chart) {
            console.log('[ChatKit] Found cached data:', cached);
            setInsight({
              summary: cached.answer || summaryText,
              chart: cached.chart || null,
              table: cached.table || null,
              sql: cached.sql || null,
              plan: null,
              lineage: null,
              warnings: cached.warnings || warnings,
              status: 'complete',
              followups: followupsData,
              chips: null,
              nqlStatus: null,
            });
          }
        })
        .catch(err => console.log('[ChatKit] No cached data:', err));
    }
  }, [chatMessages, sessionId]);

  return (
    <div className="grid h-screen grid-cols-1 gap-4 bg-gray-50 p-4 md:grid-cols-2">
      <div id="chat-pane" className="flex h-full flex-col">
        <div className="flex-1 overflow-hidden rounded-xl bg-white shadow-sm">
          {error ? (
            <div className="flex h-full items-center justify-center p-4 text-sm text-red-600">
              Chat init failed: {String(error)}
            </div>
          ) : (
            <ChatKit control={control} className="h-full w-full" />
          )}
        </div>
      </div>
      <div id="insight-pane" className="flex h-full flex-col">
        <InsightPanel data={insight} />
      </div>
    </div>
  );
}
