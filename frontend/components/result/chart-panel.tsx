import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { canRenderChart } from "@/lib/chart";
import type { ChartRecommendation } from "@/lib/types";

type ChartPanelProps = {
  chartRecommendation?: ChartRecommendation;
  columns?: string[];
  rows?: Array<Array<unknown>>;
  isLoading: boolean;
  variant?: "panel" | "embedded" | "inline";
};

type ChartRow = Record<string, string | number>;

export function ChartPanel({
  chartRecommendation,
  columns,
  rows,
  isLoading,
  variant = "panel",
}: ChartPanelProps) {
  const chartData = buildChartData(columns, rows);
  const canRender =
    chartRecommendation &&
    columns &&
    rows &&
    rows.length > 0 &&
    canRenderChart(chartRecommendation) &&
    chartData.length > 0;
  const wrapperClass =
    variant === "embedded"
      ? "rounded-[24px] border border-line bg-white/85 p-4"
      : variant === "inline"
        ? ""
        : "panel p-5";
  const showMeta = variant !== "inline";
  const showDescription = variant !== "inline";
  const showHeading = variant !== "inline";
  const chartFrameClass =
    variant === "inline"
      ? "mt-3 rounded-[20px] border border-line bg-[#fffdf9] p-4"
      : "mt-4 rounded-[24px] border border-dashed border-line bg-white/70 p-5";

  return (
    <section className={wrapperClass}>
      <div className={`${variant === "panel" ? "mt-4" : ""} flex flex-col gap-3 md:flex-row md:items-end md:justify-between`}>
        <div>
          {variant === "panel" ? <div className="eyebrow">Chart</div> : null}
          {showHeading ? (
            <h3 className={`${variant === "panel" ? "section-title mt-4" : "text-base font-semibold text-ink"}`}>Visualization</h3>
          ) : null}
          {showDescription ? (
            <p className="mt-2 text-sm leading-6 text-muted">
              This chart follows the backend recommendation instead of guessing independently.
            </p>
          ) : null}
        </div>
        {showMeta ? (
          <div className="flex flex-wrap gap-2">
            <span className="chip">
              type: {chartRecommendation?.type ?? "table_only"}
            </span>
            <span className="chip">
              x: {chartRecommendation?.x ?? "n/a"}
            </span>
            <span className="chip">
              y: {chartRecommendation?.y ?? "n/a"}
            </span>
          </div>
        ) : null}
      </div>
      <div className={chartFrameClass}>
        {isLoading ? (
          <div className="flex h-[220px] items-center justify-center text-sm text-muted">
            Waiting for chart-ready data...
          </div>
        ) : canRender && chartRecommendation?.x && chartRecommendation?.y ? (
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              {chartRecommendation.type === "line" ? (
                <LineChart data={chartData}>
                  <CartesianGrid stroke="#e2d1bd" strokeDasharray="4 4" />
                  <XAxis dataKey={chartRecommendation.x} stroke="#62574b" />
                  <YAxis stroke="#62574b" />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey={chartRecommendation.y}
                    stroke="#b14c22"
                    strokeWidth={3}
                    dot={{ r: 3 }}
                  />
                </LineChart>
              ) : (
                <BarChart data={chartData}>
                  <CartesianGrid stroke="#e2d1bd" strokeDasharray="4 4" />
                  <XAxis dataKey={chartRecommendation.x} stroke="#62574b" />
                  <YAxis stroke="#62574b" />
                  <Tooltip />
                  <Bar dataKey={chartRecommendation.y} fill="#b14c22" radius={[10, 10, 0, 0]} />
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="flex h-[220px] items-center justify-center text-sm leading-6 text-muted">
            The backend did not recommend a chart for this answer.
          </div>
        )}
      </div>
      {showDescription ? (
        <p className="mt-3 text-sm leading-6 text-muted">
          {canRender
            ? "The chart is using the backend recommendation plus the live result rows returned by /query."
            : "Charts only appear when the backend returns a useful chart recommendation with plottable rows."}
        </p>
      ) : null}
    </section>
  );
}

function buildChartData(
  columns?: string[],
  rows?: Array<Array<unknown>>,
): ChartRow[] {
  if (!columns || !rows || columns.length === 0 || rows.length === 0) {
    return [];
  }

  return rows.map((row) => {
    const chartRow: ChartRow = {};

    columns.forEach((column, index) => {
      const value = row[index];
      if (typeof value === "number") {
        chartRow[column] = value;
        return;
      }

      if (typeof value === "string") {
        const numericValue = Number(value);
        chartRow[column] = Number.isFinite(numericValue) && value.trim() !== "" ? numericValue : value;
        return;
      }

      chartRow[column] = String(value ?? "");
    });

    return chartRow;
  });
}
