const DATE_TIME_PATTERN = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(:\d{2}(\.\d+)?)?([+-]\d{2}(:?\d{2})?|Z)?$/;

/** Show a result value as text: numbers with separators, midnight timestamps as dates. */
export function formatCell(value: unknown): string {
  if (value == null) {
    return "";
  }
  if (typeof value === "number") {
    return formatNumber(value);
  }
  if (typeof value === "string") {
    const match = DATE_TIME_PATTERN.exec(value);
    if (match) {
      return match[2] === "00:00" ? match[1] : `${match[1]} ${match[2]}`;
    }
    return value;
  }
  return String(value);
}

export function formatNumber(value: number, fractionDigits?: number): string {
  if (fractionDigits != null) {
    return value.toLocaleString("en-US", {
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    });
  }
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/** 2 when any value has decimals (so 177.6 shows as 177.60 next to 221.55), else 0. */
export function sharedFractionDigits(values: number[]): number {
  return values.some((value) => !Number.isInteger(value)) ? 2 : 0;
}

export function isNumericValue(value: unknown): boolean {
  if (typeof value === "number") {
    return true;
  }
  return typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value));
}

export function rowsToDelimited(columns: string[], rows: Array<Array<unknown>>, delimiter: "," | "\t"): string {
  const escape = (value: unknown) => {
    const text = value == null ? "" : String(value);
    if (delimiter === "\t") {
      return text.replace(/[\t\n\r]+/g, " ");
    }
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [columns, ...rows].map((row) => row.map(escape).join(delimiter)).join("\n");
}

export function shortTableName(fullName: string): string {
  const parts = fullName.split(".");
  return parts[parts.length - 1] ?? fullName;
}

const SQL_CLAUSE_PATTERN =
  /\s+(?=(?:WITH|SELECT|FROM|(?:LEFT |RIGHT |FULL |INNER |CROSS )?(?:OUTER )?JOIN|WHERE|GROUP BY|HAVING|ORDER BY|LIMIT|OFFSET|UNION(?: ALL)?)\b)/gi;

/** Display-only layout: one SQL clause per line. Text inside quotes is left alone. */
export function formatSql(sql: string): string {
  if (sql.includes("\n")) {
    return sql.trim();
  }
  return sql
    .split(/('(?:[^']|'')*')/)
    .map((part, index) => (index % 2 === 1 ? part : part.replace(SQL_CLAUSE_PATTERN, "\n")))
    .join("")
    .trim();
}

