const sampleColumns = ["category", "revenue"];
const sampleRows = [
  ["Sports", "$12,000"],
  ["Animation", "$11,100"],
  ["Sci-Fi", "$10,850"],
  ["Family", "$10,430"],
];

type ResultsTableProps = {
  columns?: string[];
  rows?: Array<Array<unknown>>;
  totalRowCount?: number;
  isLoading: boolean;
  variant?: "panel" | "embedded";
};

export function ResultsTable({
  columns,
  rows,
  totalRowCount,
  isLoading,
  variant = "panel",
}: ResultsTableProps) {
  const displayColumns = columns && columns.length > 0 ? columns : sampleColumns;
  const hasLiveRows = Array.isArray(rows);
  const displayRows = hasLiveRows && rows.length > 0 ? rows : sampleRows;
  const isPlaceholder = !hasLiveRows;
  const isNoResult = hasLiveRows && rows.length === 0;
  const previewRows = displayRows.slice(0, 12);
  const wrapperClass =
    variant === "embedded" ? "rounded-[24px] border border-line bg-white/85 p-4" : "panel p-5";

  return (
    <section className={wrapperClass}>
      {variant === "panel" ? (
        <>
          <div className="eyebrow">Results</div>
          <h3 className="section-title mt-4">Tabular result preview</h3>
        </>
      ) : (
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">Result preview</p>
          <span className="chip">{previewRows.length} rows shown</span>
        </div>
      )}
      <p className={`${variant === "panel" ? "mt-3" : "mb-4"} text-sm leading-6 text-muted`}>
        {isLoading
          ? "Waiting for row data from the backend."
          : isNoResult
            ? "The query ran successfully but returned no matching rows."
          : isPlaceholder
            ? "No live result yet. These placeholder rows show how the result table will look."
            : `Rendering a preview of ${previewRows.length} rows from a total of ${totalRowCount ?? displayRows.length} returned by the backend.`}
      </p>
      {!isNoResult ? (
      <div className="mt-4 overflow-hidden rounded-[24px] border border-line">
        <div className="overflow-x-auto">
        <table className="min-w-full border-collapse bg-white">
          <thead>
            <tr className="bg-accentSoft text-left text-sm text-ink">
              {displayColumns.map((column) => (
                <th key={column} className="border-b border-line px-4 py-3 font-semibold">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {previewRows.map((row, rowIndex) => (
              <tr
                key={`${rowIndex}-${String(row[0] ?? "row")}`}
                className="text-sm text-muted"
              >
                {row.map((value, cellIndex) => (
                  <td
                    key={`${rowIndex}-${cellIndex}`}
                    className="border-b border-line px-4 py-3 last:border-b-0"
                  >
                    {String(value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>
      ) : null}
      {!isPlaceholder && !isNoResult && displayRows.length > previewRows.length ? (
        <p className="mt-3 text-sm leading-6 text-muted">
          Only the first {previewRows.length} rows are shown in the preview. The backend
          may still return more rows within its response cap.
        </p>
      ) : null}
    </section>
  );
}
