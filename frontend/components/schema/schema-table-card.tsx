import type { SchemaTableSummary } from "@/lib/types";

export function SchemaTableCard({
  name,
  schema_name,
  description,
  columns,
  primary_key,
  foreign_keys,
}: SchemaTableSummary) {
  const highlightColumns = columns.slice(0, 6);

  return (
    <article className="panel p-5">
      <div className="eyebrow">Table</div>
      <h2 className="mt-4 font-serif text-[1.4rem] leading-tight tracking-[-0.03em] text-ink">
        {name}
      </h2>
      <p className="mt-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted">
        schema: {schema_name}
      </p>
      <p className="mt-3 text-sm leading-6 text-muted">
        {description ?? "No table description is available for this schema object."}
      </p>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <InfoBadge label="Columns" value={String(columns.length)} />
        <InfoBadge label="Primary key" value={primary_key.length > 0 ? primary_key.join(", ") : "none"} />
        <InfoBadge label="Foreign keys" value={String(foreign_keys.length)} />
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        {highlightColumns.map((column) => (
          <span key={column.name} className="chip">
            {column.name}
          </span>
        ))}
      </div>
      {foreign_keys.length > 0 ? (
        <div className="mt-5 space-y-2">
          {foreign_keys.slice(0, 2).map((foreignKey) => (
            <div
              key={foreignKey.name}
              className="rounded-[18px] border border-line bg-white/75 px-4 py-3 text-sm leading-6 text-muted"
            >
              <strong className="text-ink">{foreignKey.name}</strong>
              <div>
                {foreignKey.columns.join(", ")} → {foreignKey.references_schema}.
                {foreignKey.references_table} ({foreignKey.references_columns.join(", ")})
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

type InfoBadgeProps = {
  label: string;
  value: string;
};

function InfoBadge({ label, value }: InfoBadgeProps) {
  return (
    <div className="rounded-[18px] border border-line bg-white/80 px-3 py-3">
      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-muted">{label}</p>
      <p className="mt-2 text-sm font-semibold leading-6 text-ink">{value}</p>
    </div>
  );
}
