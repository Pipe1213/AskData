import type { ChartRecommendation } from "@/lib/types";

type QueryMetricsProps = {
  rowCount: number;
  columnCount: number;
  warningCount: number;
  tableCount: number;
  chartRecommendation?: ChartRecommendation;
  isPlaceholder: boolean;
};

export function QueryMetrics({
  rowCount,
  columnCount,
  warningCount,
  tableCount,
  chartRecommendation,
  isPlaceholder,
}: QueryMetricsProps) {
  const chartLabel = chartRecommendation?.type ?? "table_only";

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        label="Rows"
        value={String(rowCount)}
        note={isPlaceholder ? "Example preview" : "From latest response"}
      />
      <MetricCard
        label="Columns"
        value={String(columnCount)}
        note={isPlaceholder ? "Example preview" : "Result shape"}
      />
      <MetricCard
        label="Chart"
        value={chartLabel.replace("_", " ")}
        note="Backend recommendation"
      />
      <MetricCard
        label="Trust"
        value={`${warningCount} warnings / ${tableCount} tables`}
        note="Right-rail metadata"
      />
    </div>
  );
}

type MetricCardProps = {
  label: string;
  value: string;
  note: string;
};

function MetricCard({ label, value, note }: MetricCardProps) {
  return (
    <div className="rounded-[24px] border border-line bg-white/80 px-4 py-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">{label}</p>
      <p className="mt-2 font-serif text-2xl leading-none tracking-[-0.03em] text-ink">
        {value}
      </p>
      <p className="mt-2 text-sm leading-6 text-muted">{note}</p>
    </div>
  );
}
