import { formatNumber, sharedFractionDigits } from "@/lib/format";

const MAX_BARS = 25;

type BarListProps = {
  label: string;
  items: Array<{ label: string; value: number }>;
};

/** Horizontal bars with the labels on the left, so long names wrap instead of being cut. */
export function BarList({ label, items }: BarListProps) {
  const shown = items.slice(0, MAX_BARS);
  const max = Math.max(...shown.map((item) => Math.abs(item.value)), 0);
  const digits = sharedFractionDigits(shown.map((item) => item.value));

  return (
    <div className="flex flex-col gap-2">
      <div role="img" aria-label={label} className="flex flex-col gap-2">
        {shown.map((item, index) => (
          <div
            key={`${item.label}-${index}`}
            className="grid grid-cols-[minmax(80px,35%)_minmax(0,1fr)_auto] items-center gap-3 text-sm"
          >
            <span className="break-words leading-tight text-inkSoft">{item.label}</span>
            <div className="h-5 overflow-hidden rounded bg-track">
              <div
                className="h-full rounded bg-accent"
                style={{ width: max > 0 ? `${(Math.abs(item.value) / max) * 100}%` : "0%" }}
              />
            </div>
            <span className="text-right font-mono text-[13px] text-ink">{formatNumber(item.value, digits)}</span>
          </div>
        ))}
      </div>
      {items.length > shown.length ? (
        <p className="m-0 text-[13px] text-muted">
          Showing the first {shown.length} of {items.length}. The table has all of them.
        </p>
      ) : null}
    </div>
  );
}
