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
  isLoading: boolean;
};

export function ResultsTable({
  columns,
  rows,
  isLoading,
}: ResultsTableProps) {
  const displayColumns = columns && columns.length > 0 ? columns : sampleColumns;
  const displayRows = rows && rows.length > 0 ? rows : sampleRows;
  const isPlaceholder = !rows || rows.length === 0;
  const previewRows = displayRows.slice(0, 12);

  return (
    <section className="panel p-5">
      <div className="eyebrow">Results</div>
      <h3 className="section-title mt-4">Tabular result preview</h3>
      <p className="mt-3 text-sm leading-6 text-muted">
        {isLoading
          ? "Waiting for row data from the backend."
          : isPlaceholder
            ? "No live result yet. These placeholder rows show how the result table will look."
            : `Rendering a preview of ${previewRows.length} rows from a total of ${displayRows.length} returned by the backend.`}
      </p>
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
                {row.map((value) => (
                  <td
                    key={`${rowIndex}-${String(value)}`}
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
      {!isPlaceholder && displayRows.length > previewRows.length ? (
        <p className="mt-3 text-sm leading-6 text-muted">
          Only the first {previewRows.length} rows are shown in the workspace preview. The backend
          may still return more rows within its response cap.
        </p>
      ) : null}
    </section>
  );
}
