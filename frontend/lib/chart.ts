import type { ChartRecommendation } from "@/lib/types";

export function canRenderChart(chart: ChartRecommendation): boolean {
  return chart.type !== "table_only" && Boolean(chart.x) && Boolean(chart.y);
}
