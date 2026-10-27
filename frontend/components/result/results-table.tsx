import { formatCell, isNumericValue } from "@/lib/format";

const MAX_TABLE_ROWS = 50;

type ResultsTableProps = {
  columns: string[];
  rows: Array<Array<unknown>>;
  totalRowCount: number;
};

export function ResultsTable({ columns, rows, totalRowCount }: ResultsTableProps) {
  const shown = rows.slice(0, MAX_TABLE_ROWS);
  const numericColumns = columns.map((_, index) => shown.length > 0 && shown.every((row) => row[index] == null || isNumericValue(row[index])));

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto rounded-[10px] border border-line">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr className="bg-sidebar text-left">
              {columns.map((column, index) => (
                <th
                  key={column}
                  scope="col"
                  className={`whitespace-nowrap border-b border-line px-3 py-2 font-medium text-ink ${numericColumns[index] ? "text-right" : ""}`}
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-b border-line last:border-b-0">
                {row.map((value, cellIndex) => (
                  <td
                    key={cellIndex}
                    className={`px-3 py-2 text-inkSoft ${numericColumns[cellIndex] ? "text-right font-mono text-[13px]" : ""}`}
                  >
                    {formatCell(value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalRowCount > shown.length ? (
        <p className="m-0 text-[13px] text-muted">
          Showing {shown.length} of {totalRowCount} rows. Download CSV for all of them.
        </p>
      ) : null}
    </div>
  );
}
