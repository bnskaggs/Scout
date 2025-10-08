"use client";

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Tooltip,
  Legend,
  ChartOptions,
  ChartData,
} from "chart.js";
import { Bar, Line } from "react-chartjs-2";
import { useMemo } from "react";

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, Tooltip, Legend);

export type ChartRow = Record<string, unknown>;

export type InsightChart = {
  type?: string;
  x: string;
  y: string;
  data?: ChartRow[];
};

export type ChartRendererProps = {
  chart: InsightChart | null | undefined;
};

function formatLabelValue(value: unknown, formatter: Intl.DateTimeFormat | null) {
  if (formatter && typeof value === "string") {
    const date = new Date(value);
    if (!Number.isNaN(date.valueOf())) {
      return formatter.format(date);
    }
  }
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

export function ChartRenderer({ chart }: ChartRendererProps) {
  const { chartData, chartOptions, type } = useMemo(() => {
    if (!chart || !Array.isArray(chart.data) || chart.data.length === 0) {
      return { chartData: null, chartOptions: null, type: chart?.type ?? "bar" } as {
        chartData: ChartData<"bar"> | ChartData<"line"> | null;
        chartOptions: ChartOptions<"bar"> | ChartOptions<"line"> | null;
        type: string;
      };
    }

    const xKey = chart.x;
    const yKey = chart.y;
    const dateFormatter = chart.x === "month" ? new Intl.DateTimeFormat(undefined, { month: "short", year: "numeric" }) : null;
    const labels = chart.data.map((row: ChartRow) => formatLabelValue(row[xKey], dateFormatter));
    const values = chart.data.map((row: ChartRow) => {
      const numeric = Number(row[yKey]);
      return Number.isFinite(numeric) ? numeric : 0;
    });

    const datasetConfig =
      chart.type === "line"
        ? {
            label: yKey,
            data: values,
            borderColor: "rgba(239, 68, 68, 1)",
            backgroundColor: "rgba(239, 68, 68, 0.2)",
            borderWidth: 2,
            pointRadius: 4,
            tension: 0.3,
            fill: false,
          }
        : {
            label: yKey,
            data: values,
            backgroundColor: "rgba(37, 99, 235, 0.6)",
            borderColor: "rgba(37, 99, 235, 1)",
            borderWidth: 1,
            borderSkipped: false as const,
          };

    const options: ChartOptions<"bar"> | ChartOptions<"line"> = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        tooltip: { enabled: true },
        legend: { display: true },
      },
      scales: {
        y: {
          beginAtZero: true,
        },
      },
    };

    const data: ChartData<"bar"> | ChartData<"line"> = {
      labels,
      datasets: [datasetConfig],
    };

    return { chartData: data, chartOptions: options, type: chart.type ?? "bar" };
  }, [chart]);

  if (!chart || !chartData || !chartOptions) {
    return (
      <div className="mt-4 flex h-96 w-full items-center justify-center rounded-lg border border-dashed border-gray-200 bg-white text-sm text-gray-500">
        No chart data available.
      </div>
    );
  }

  const ChartComponent = type === "line" ? Line : Bar;

  return (
    <div className="mt-4 h-96 w-full">
      <ChartComponent data={chartData} options={chartOptions} />
    </div>
  );
}

export default ChartRenderer;
