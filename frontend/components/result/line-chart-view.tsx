import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatNumber } from "@/lib/format";

type LineChartViewProps = {
  label: string;
  seriesName: string;
  points: Array<{ x: string; y: number }>;
};

const MONO = "var(--font-plex-mono), Consolas, monospace";

export function LineChartView({ label, seriesName, points }: LineChartViewProps) {
  // Monthly series ("2022-02-01", "2022-03-01", ...) read better as "2022-02".
  const monthly = points.length > 0 && points.every((point) => /^\d{4}-\d{2}-01$/.test(point.x));
  const data = monthly ? points.map((point) => ({ ...point, x: point.x.slice(0, 7) })) : points;

  return (
    <div role="img" aria-label={label} className="h-[240px] w-full overflow-hidden">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#E2DFD8" vertical={false} />
          <XAxis
            dataKey="x"
            stroke="#5E5B55"
            tick={{ fontSize: 12, fontFamily: MONO }}
            tickLine={false}
            minTickGap={16}
          />
          <YAxis
            stroke="#5E5B55"
            tick={{ fontSize: 12, fontFamily: MONO }}
            tickLine={false}
            axisLine={false}
            width={56}
            tickFormatter={(value: number) => formatNumber(value)}
          />
          <Tooltip
            formatter={(value) => formatNumber(Number(value))}
            contentStyle={{ borderRadius: 10, borderColor: "#E2DFD8", fontSize: 13 }}
          />
          <Line type="monotone" dataKey="y" name={seriesName} stroke="#9C3F1A" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
