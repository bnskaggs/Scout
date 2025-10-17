"use client";

import { useState, useRef, useEffect } from "react";
import InsightPanel, { InsightPanelData } from "./components/InsightPanel";

type Message = {
  role: "user" | "assistant";
  content: string;
  data?: InsightPanelData;
  clarification?: {
    question: string;
    suggested_answers: string[];
  };
};

type Conversation = {
  id: string;
  name: string;
  sessionId: string;
  messages: Message[];
  createdAt: Date;
};

/**
 * Simple chat interface with multi-turn conversation support.
 * Uses /chat/complete endpoint for context-aware conversations.
 *
 * Access at: http://localhost:3000/
 */
const createConversation = (): Conversation => ({
  id: `conv-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
  name: "New conversation",
  sessionId: `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
  messages: [],
  createdAt: new Date(),
});

export default function SimpleChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>(() => {
    const initialConv = createConversation();
    return [initialConv];
  });
  const [activeConversationId, setActiveConversationId] = useState<string>("");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [insight, setInsight] = useState<InsightPanelData | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Initialize activeConversationId once conversations are set
  useEffect(() => {
    if (!activeConversationId && conversations.length > 0) {
      setActiveConversationId(conversations[0].id);
    }
  }, [conversations, activeConversationId]);

  const activeConversation = conversations.find(c => c.id === activeConversationId) || conversations[0];
  const messages = activeConversation?.messages || [];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const updateConversationMessages = (conversationId: string, updater: (messages: Message[]) => Message[]) => {
    setConversations(prev =>
      prev.map(conv =>
        conv.id === conversationId
          ? { ...conv, messages: updater(conv.messages) }
          : conv
      )
    );
  };

  const autoNameConversation = (conversationId: string, firstMessage: string) => {
    const name = firstMessage.length > 30
      ? firstMessage.substring(0, 30) + "..."
      : firstMessage;

    setConversations(prev =>
      prev.map(conv =>
        conv.id === conversationId && conv.name === "New conversation"
          ? { ...conv, name }
          : conv
      )
    );
  };

  const createNewConversation = () => {
    const newConv = createConversation();
    setConversations(prev => [newConv, ...prev]);
    setActiveConversationId(newConv.id);
    setInsight(null);
  };

  const switchConversation = (conversationId: string) => {
    setActiveConversationId(conversationId);
    const conv = conversations.find(c => c.id === conversationId);
    if (conv && conv.messages.length > 0) {
      const lastMessage = conv.messages[conv.messages.length - 1];
      if (lastMessage.role === "assistant" && lastMessage.data) {
        setInsight(lastMessage.data);
      }
    } else {
      setInsight(null);
    }
  };

  const handleClarificationClick = async (answer: string) => {
    if (loading) return;
    updateConversationMessages(activeConversation.id, (prev) => [...prev, { role: "user", content: answer }]);
    setLoading(true);
    await sendMessage(answer);
  };

  const handleFollowupClick = (question: string) => {
    if (loading) return;
    setInput(question);
  };

  const sendMessage = async (message: string) => {
    try {
      const response = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: message,
          session_id: activeConversation.sessionId,
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
        status: data.status || "complete",
        followups: null,
        chips: data.chips || null,
        nqlStatus: data.nql_status || null,
      };

      setInsight(insightData);

      // Add assistant message with clarification if needed
      const assistantMessage: Message = {
        role: "assistant",
        content: data.status === "clarification_needed"
          ? data.question || "Please clarify your request"
          : data.summary || "Query completed",
        data: insightData,
      };

      if (data.status === "clarification_needed" && data.question && data.suggested_answers) {
        assistantMessage.clarification = {
          question: data.question,
          suggested_answers: data.suggested_answers,
        };
      }

      updateConversationMessages(activeConversation.id, (prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Error:", error);
      const errorMessage = error instanceof Error ? error.message : "Unknown error";
      updateConversationMessages(activeConversation.id, (prev) => [
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput("");

    // Auto-name conversation on first message
    if (activeConversation.messages.length === 0) {
      autoNameConversation(activeConversation.id, userMessage);
    }

    updateConversationMessages(activeConversation.id, (prev) => [...prev, { role: "user", content: userMessage }]);
    setLoading(true);
    await sendMessage(userMessage);
  };

  return (
    <div className="grid h-screen grid-cols-1 gap-4 bg-gray-50 p-4 md:grid-cols-2">
      {/* Chat Panel */}
      <div className="flex h-full flex-col relative">
        {/* Conversations Sidebar */}
        {historyOpen && (
          <div className="absolute left-0 top-0 bottom-0 w-64 bg-white shadow-lg rounded-xl z-10 overflow-hidden flex flex-col">
            <div className="border-b border-gray-200 px-4 py-3 flex items-center justify-between">
              <h3 className="font-semibold text-gray-900">Conversations</h3>
              <button
                onClick={() => setHistoryOpen(false)}
                className="text-gray-500 hover:text-gray-700"
              >
                ✕
              </button>
            </div>
            <div className="p-3 border-b border-gray-200">
              <button
                onClick={createNewConversation}
                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
              >
                + New Conversation
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  onClick={() => switchConversation(conv.id)}
                  className={`p-3 rounded-lg cursor-pointer text-sm transition-colors ${
                    conv.id === activeConversationId
                      ? "bg-blue-100 border border-blue-300"
                      : "bg-gray-50 hover:bg-gray-100"
                  }`}
                >
                  <div className={`font-medium line-clamp-1 ${
                    conv.id === activeConversationId ? "text-blue-900" : "text-gray-900"
                  }`}>
                    {conv.name}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {conv.messages.length} message{conv.messages.length !== 1 ? 's' : ''}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex-1 overflow-hidden rounded-xl bg-white shadow-sm flex flex-col">
          <div className="border-b border-gray-200 bg-white px-6 py-4 flex items-center justify-between">
            <div>
              <h1 className="text-xl font-semibold text-gray-900">
                Scout Analytics Agent
              </h1>
              <p className="text-sm text-gray-600">
                Ask questions about your data • Multi-turn conversations enabled
              </p>
            </div>
            <button
              onClick={() => setHistoryOpen(!historyOpen)}
              className="ml-4 px-3 py-1.5 text-sm rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-700"
            >
              {historyOpen ? "Close" : "Conversations"}
            </button>
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
              <div key={idx}>
                <div
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
                {msg.clarification && (
                  <div className="flex justify-start mt-2">
                    <div className="max-w-[80%] space-y-2">
                      <p className="text-xs text-gray-600 font-medium">Select an option:</p>
                      <div className="flex flex-wrap gap-2">
                        {msg.clarification.suggested_answers.map((answer, answerIdx) => (
                          <button
                            key={answerIdx}
                            onClick={() => handleClarificationClick(answer)}
                            disabled={loading}
                            className="rounded-full bg-indigo-50 border border-indigo-300 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {answer}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
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
        <InsightPanel data={insight} onFollowupClick={handleFollowupClick} />
      </div>
    </div>
  );
}
