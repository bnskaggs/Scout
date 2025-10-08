"use client";

import { useState } from "react";
import InsightPanel, { InsightPanelData } from "../components/InsightPanel";

/**
 * Simple test page to verify the tool endpoint works
 * without needing ChatKit workflow configuration.
 *
 * Access at: http://localhost:3000/test
 */
export default function TestPage() {
  const [question, setQuestion] = useState("Show me total incidents last year");
  const [loading, setLoading] = useState(false);
  const [insight, setInsight] = useState<InsightPanelData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/tools/truesight-query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          utterance: question,
          session_id: `test-${Date.now()}`,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${await response.text()}`);
      }

      const data = await response.json();
      console.log("Tool response:", data);

      setInsight({
        summary: data.answer || "Query completed",
        chart: data.chart || null,
        table: data.table || null,
        sql: data.sql || null,
        plan: null,
        lineage: null,
        warnings: data.warnings || [],
        status: data.status || "complete",
        followups: null,
        chips: null,
        nqlStatus: null,
      });
    } catch (err) {
      console.error("Error:", err);
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid h-screen grid-cols-1 gap-4 bg-gray-50 p-4 md:grid-cols-2">
      <div className="flex h-full flex-col">
        <div className="mb-4 rounded-xl bg-white p-6 shadow-sm">
          <h1 className="mb-4 text-2xl font-bold text-gray-900">
            TrueSight Tool Test
          </h1>
          <p className="mb-4 text-sm text-gray-600">
            This page tests the tool endpoint directly without ChatKit.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="question"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                Ask a question:
              </label>
              <input
                id="question"
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Show me incidents by area"
              />
            </div>

            <button
              type="submit"
              disabled={loading || !question.trim()}
              className="w-full rounded-lg bg-blue-600 px-4 py-2 text-white font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {loading ? "Loading..." : "Run Query"}
            </button>
          </form>

          {error && (
            <div className="mt-4 rounded-lg bg-red-50 border border-red-200 p-4">
              <p className="text-sm text-red-800">
                <strong>Error:</strong> {error}
              </p>
            </div>
          )}

          <div className="mt-6 space-y-2">
            <p className="text-sm font-medium text-gray-700">Try these:</p>
            <div className="flex flex-wrap gap-2">
              {[
                "Show me total incidents",
                "Incidents by area last year",
                "Crime breakdown by type",
                "Monthly trend of incidents",
              ].map((q) => (
                <button
                  key={q}
                  onClick={() => setQuestion(q)}
                  className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700 hover:bg-gray-200"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-auto rounded-xl bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">
            Debug Info
          </h2>
          <div className="space-y-2 text-sm">
            <div>
              <strong>Backend:</strong>{" "}
              <span className="font-mono text-xs">
                {process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"}
              </span>
            </div>
            <div>
              <strong>Endpoint:</strong>{" "}
              <span className="font-mono text-xs">
                /api/tools/truesight-query
              </span>
            </div>
            <div>
              <strong>Status:</strong>{" "}
              {loading ? (
                <span className="text-yellow-600">Loading...</span>
              ) : error ? (
                <span className="text-red-600">Error</span>
              ) : insight ? (
                <span className="text-green-600">Success</span>
              ) : (
                <span className="text-gray-500">Ready</span>
              )}
            </div>
          </div>

          {insight && (
            <div className="mt-4">
              <h3 className="mb-2 font-medium text-gray-900">Raw Response:</h3>
              <pre className="overflow-auto rounded bg-gray-100 p-2 text-xs">
                {JSON.stringify(insight, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>

      <div className="flex h-full flex-col">
        <InsightPanel data={insight} />
      </div>
    </div>
  );
}
