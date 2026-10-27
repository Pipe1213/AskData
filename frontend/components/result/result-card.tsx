"use client";

import { useState } from "react";

import { BarList } from "@/components/result/bar-list";
import { LineChartView } from "@/components/result/line-chart-view";
import { ResultsTable } from "@/components/result/results-table";
import { canRenderChart } from "@/lib/chart";
import { formatCell, rowsToDelimited } from "@/lib/format";
import type { QueryResponse } from "@/lib/types";

type ResultCardProps = {
  response: QueryResponse;
  onDownloadCsv: () => void;
};

type ViewMode = "chart" | "table";

export function ResultCard({ response, onDownloadCsv }: ResultCardProps) {
  const chart = response.chart_recommendation;
  const xIndex = chart.x ? response.columns.indexOf(chart.x) : -1;
  const yIndex = chart.y ? response.columns.indexOf(chart.y) : -1;
  const hasChart = canRenderChart(chart) && xIndex >= 0 && yIndex >= 0 && response.rows.length > 1;
  const [view, setView] = useState<ViewMode>(hasChart ? "chart" : "table");
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(rowsToDelimited(response.columns, response.rows, "\t"));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  const chartLabel = hasChart
    ? `${chart.type === "line" ? "Line" : "Bar"} chart of ${chart.y} by ${chart.x}, ${response.rows.length} points. The table view has the values.`
    : "";

  return (
    <section className="flex flex-col gap-4 rounded-[14px] border border-line bg-surface px-4 pb-5 pt-4 md:px-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {hasChart ? (
          <div role="group" aria-label="View" className="flex rounded-[10px] bg-sidebar p-[3px]">
            {(["chart", "table"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                aria-pressed={view === mode}
                onClick={() => setView(mode)}
                className={`h-9 rounded-lg px-4 text-sm font-medium ${
                  view === mode ? "bg-surface text-ink shadow-[0_1px_2px_rgba(0,0,0,0.08)]" : "text-inkSoft"
                }`}
              >
                {mode === "chart" ? "Chart" : "Table"}
              </button>
            ))}
          </div>
        ) : (
          <span className="text-sm text-muted">
            {response.row_count} {response.row_count === 1 ? "row" : "rows"}
          </span>
        )}
        <div className="flex gap-1">
          <button
            type="button"
            onClick={handleCopy}
            className="h-9 rounded-lg px-2.5 text-[13px] font-medium text-inkSoft hover:bg-sidebar hover:text-ink"
          >
            {copied ? "Copied" : "Copy"}
          </button>
          <button
            type="button"
            onClick={onDownloadCsv}
            className="h-9 rounded-lg px-2.5 text-[13px] font-medium text-inkSoft hover:bg-sidebar hover:text-ink"
          >
            Download CSV
          </button>
        </div>
      </div>

      {hasChart && view === "chart" ? (
        chart.type === "line" ? (
          <LineChartView
            label={chartLabel}
            seriesName={chart.y ?? "value"}
            points={response.rows.map((row) => ({ x: formatCell(row[xIndex]), y: toNumber(row[yIndex]) }))}
          />
        ) : (
          <BarList
            label={chartLabel}
            items={response.rows.map((row) => ({ label: barLabel(response.columns, row, xIndex), value: toNumber(row[yIndex]) }))}
          />
        )
      ) : (
        <ResultsTable columns={response.columns} rows={response.rows} totalRowCount={response.row_count} />
      )}
    </section>
  );
}

/** A first-name label gets the matching last name when the result has one ("Karl Seal", not "KARL"). */
function barLabel(columns: string[], row: Array<unknown>, xIndex: number): string {
  const label = formatCell(row[xIndex]);
  const xColumn = columns[xIndex] ?? "";
  if (!/first_?name$/i.test(xColumn)) {
    return label;
  }
  const lastIndex = columns.findIndex((column) => /last_?name$/i.test(column));
  const full = lastIndex >= 0 ? `${label} ${formatCell(row[lastIndex])}` : label;
  return full === full.toUpperCase() ? toTitleCase(full) : full;
}

function toTitleCase(text: string): string {
  return text.toLowerCase().replace(/(^|[\s'-])(\p{L})/gu, (_, start: string, letter: string) => start + letter.toUpperCase());
}

function toNumber(value: unknown): number {
  if (typeof value === "number") {
    return value;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
