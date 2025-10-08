"use client";

import { useState, useRef, useEffect } from "react";
import InsightPanel, { InsightPanelData } from "../components/InsightPanel";

type Message = {
  role: "user" | "assistant";
  content: string;
  data?: InsightPanelData;
};

/**
 * Simple chat interface with multi-turn conversation support.
 * Uses /chat/complete endpoint for context-aware conversations.
 *
 * Access at: http://localhost:3000/simple
 */
export default function SimpleChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId] = useState(() => `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);
  const [insight, setInsight] = useState<InsightPanelData | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setLoading(true);

    try {
      const response = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMessage,
          session_id: sessionId,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `HTTP ${response.status}`);
      }

      const data = await response.json();
      console.log("Agent response:", data);

      // Create insight data
      const insightData: InsightPanelData = {
        summary: data.summary || "",
        chart: data.chart || null,
        table: data.table || null,
        sql: data.sql || null,
        plan: null,
        lineage: null,
        warnings: data.warnings || [],
        status: "complete",
        followups: null,
        chips: null,
        nqlStatus: null,
      };

      setInsight(insightData);

      // Add assistant message
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.summary || "Query completed",
          data: insightData,
        },
      ]);
    } catch (error) {
      console.error("Error:", error);
      const errorMessage = error instanceof Error ? error.message : "Unknown error";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${errorMessage}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid h-screen grid-cols-1 gap-4 bg-gray-50 p-4 md:grid-cols-2">
      {/* Chat Panel */}
      <div className="flex h-full flex-col">
        <div className="flex-1 overflow-hidden rounded-xl bg-white shadow-sm flex flex-col">
          <div className="border-b border-gray-200 bg-white px-6 py-4">
            <h1 className="text-xl font-semibold text-gray-900">
              Scout Analytics Agent
            </h1>
            <p className="text-sm text-gray-600">
              Ask questions about your data • Multi-turn conversations enabled
            </p>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {messages.length === 0 && (
              <div className="text-center text-gray-500 text-sm mt-8">
                <p className="mb-4">Ask a question to get started!</p>
                <div className="flex flex-wrap gap-2 justify-center">
                  {[
                    "Show me total incidents",
                    "Incidents by area last year",
                    "Crime trends over time",
                  ].map((q) => (
                    <button
                      key={q}
                      onClick={() => setInput(q)}
                      className="rounded-full bg-blue-50 px-3 py-1 text-xs text-blue-700 hover:bg-blue-100"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-2 ${
                    msg.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 text-gray-900"
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="bg-gray-100 rounded-lg px-4 py-2">
                  <p className="text-sm text-gray-600">Thinking...</p>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-gray-200 bg-white p-4">
            <form onSubmit={handleSubmit} className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a question..."
                className="flex-1 rounded-lg border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="rounded-lg bg-blue-600 px-6 py-2 text-white font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                Send
              </button>
            </form>
          </div>
        </div>
      </div>

      {/* Insight Panel */}
      <div className="flex h-full flex-col">
        <InsightPanel data={insight} />
      </div>
    </div>
  );
}
