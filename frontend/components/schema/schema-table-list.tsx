import type { SchemaTableSummary } from "@/lib/types";

import { SchemaTableCard } from "@/components/schema/schema-table-card";

type SchemaTableListProps = {
  tables: SchemaTableSummary[];
};

export function SchemaTableList({ tables }: SchemaTableListProps) {
  return (
    <section className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
      {tables.map((table) => (
        <SchemaTableCard key={table.name} {...table} />
      ))}
    </section>
  );
}
