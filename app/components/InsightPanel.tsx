"use client";

import { useMemo } from "react";
import ChartRenderer, { InsightChart } from "./ChartRenderer";
import TableRenderer from "./TableRenderer";

type InsightChips = {
  time?: string[];
  dimensions?: string[];
  filters?: string[];
};

type NqlStatus = {
  valid?: boolean;
  attempted?: boolean;
  stage?: string;
  reason?: string;
  fallback?: string;
  detail?: string;
};

export type InsightPanelData = {
  summary?: string;
  chart?: InsightChart | null;
  table?: Array<Record<string, unknown>> | null;
  sql?: string | null;
  plan?: unknown;
  lineage?: unknown;
  warnings?: string[] | null;
  status?: string | null;
  followups?: string[] | null;
  chips?: InsightChips | null;
  nqlStatus?: NqlStatus | null;
};

export type InsightPanelProps = {
  data: InsightPanelData | null;
};

function formatStructuredValue(value: unknown) {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch (err) {
    return String(value);
  }
}

function buildNqlStatusMessage(status: NqlStatus | null | undefined) {
  if (!status) return null;
  if (status.valid || status.valid === undefined) {
    if (status.attempted === undefined && status.reason === undefined) {
      return null;
    }
  }

  if (status.attempted === false) {
    const reason = status.reason || "nql_not_attempted";
    return `NQL not used (${reason})`;
  }

  if (status.valid) {
    return null;
  }

  const stage = status.stage ? status.stage.toUpperCase() : "UNKNOWN";
  const reason = status.reason || "error";
  const fallback = status.fallback ? status.fallback.toUpperCase() : "LEGACY";
  return `NQL fallback (${stage}): ${reason} → ${fallback}`;
}

function renderChips(chips: InsightChips | null | undefined) {
  if (!chips) return null;
  const items: Array<{ label: string; value: string }> = [];

  (chips.time ?? []).forEach((value) => items.push({ label: "Time", value }));
  (chips.dimensions ?? []).forEach((value) => items.push({ label: "Dimensions", value }));
  (chips.filters ?? []).forEach((value) => items.push({ label: "Filters", value }));

  if (items.length === 0) return null;

  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {items.map((item, index) => (
        <span
          key={`${item.label}-${item.value}-${index}`}
          className="inline-flex items-center rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700"
        >
          <span className="mr-1 text-slate-500">{item.label}:</span>
          {item.value}
        </span>
      ))}
    </div>
  );
}

export function InsightPanel({ data }: InsightPanelProps) {
  const warnings = useMemo(() => (Array.isArray(data?.warnings) ? data?.warnings.filter(Boolean) : []), [data?.warnings]);
  const followups = useMemo(() => (Array.isArray(data?.followups) ? data?.followups.filter(Boolean) : []), [data?.followups]);
  const needsClarification = data?.status === "clarification_needed";

  const nqlStatusMessage = useMemo(() => buildNqlStatusMessage(data?.nqlStatus), [data?.nqlStatus]);

  if (!data) {
    return (
      <div className="flex h-full flex-col rounded-xl border border-dashed border-gray-300 bg-white p-6 text-center text-sm text-gray-500 shadow-sm">
        <div className="m-auto max-w-sm space-y-2">
          <h2 className="text-lg font-semibold text-gray-700">Insight Panel</h2>
          <p className="text-gray-500">Run a query in the chat to see visualizations and query details here.</p>
        </div>
      </div>
    );
  }

  const summary = data.summary?.trim();
  const plan = formatStructuredValue(data.plan);
  const lineage = formatStructuredValue(data.lineage);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl bg-white shadow-sm">
      <div className="flex-1 overflow-y-auto p-6">
        <div className="space-y-6">
          <header>
            <h2 className="text-xl font-semibold text-gray-900">Insight</h2>
            <p className="mt-2 text-base text-gray-700">{summary || "Awaiting the latest insight..."}</p>
            {needsClarification ? (
              <div className="mt-4 rounded-lg border border-indigo-300 bg-indigo-50 p-4 text-sm text-indigo-800">
                <p className="font-medium">More detail is required to continue.</p>
                <p className="mt-1 text-indigo-700">Respond in chat to clarify your request.</p>
              </div>
            ) : null}
            {renderChips(data.chips ?? null)}
            {followups.length > 0 ? (
              <div className="mt-4">
                <p className="text-sm font-medium text-gray-600">You might also ask:</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {followups.map((item, index) => (
                    <span
                      key={`${item}-${index}`}
                      className="inline-flex items-center rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </header>

          {nqlStatusMessage ? (
            <div
              className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800"
              title={data?.nqlStatus?.detail}
            >
              {nqlStatusMessage}
            </div>
          ) : null}

          {warnings.length > 0 ? (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
              <h3 className="mb-2 text-base font-semibold">⚠️ Warnings</h3>
              <ul className="list-disc space-y-1 pl-5">
                {warnings.map((warning, index) => (
                  <li key={`${warning}-${index}`}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <section>
            <h3 className="text-lg font-semibold text-gray-900">Chart</h3>
            <ChartRenderer chart={data.chart ?? null} />
          </section>

          <section>
            <h3 className="text-lg font-semibold text-gray-900">Table</h3>
            <TableRenderer rows={data.table ?? null} />
          </section>

          <section>
            <details className="group rounded-lg border border-gray-200 bg-gray-50 p-4" open>
              <summary className="cursor-pointer text-base font-semibold text-gray-900">
                How this was computed
              </summary>
              <div className="mt-4 space-y-4 text-sm">
                <div>
                  <h4 className="text-sm font-semibold text-gray-800">SQL</h4>
                  <pre className="mt-2 overflow-auto rounded-md bg-gray-900 p-4 text-xs text-gray-100">
                    {data.sql || "No SQL available."}
                  </pre>
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-gray-800">Plan</h4>
                  <pre className="mt-2 overflow-auto rounded-md bg-gray-900 p-4 text-xs text-gray-100">
                    {plan || "No plan available."}
                  </pre>
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-gray-800">Lineage</h4>
                  <pre className="mt-2 overflow-auto rounded-md bg-gray-900 p-4 text-xs text-gray-100">
                    {lineage || "No lineage available."}
                  </pre>
                </div>
              </div>
            </details>
          </section>
        </div>
      </div>
    </div>
  );
}

export default InsightPanel;
