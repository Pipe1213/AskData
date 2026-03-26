type UsedTablesPanelProps = {
  title: string;
  description: string;
  tables: string[];
  variant?: "panel" | "compact";
};

export function UsedTablesPanel({
  title,
  description,
  tables,
  variant = "panel",
}: UsedTablesPanelProps) {
  const wrapperClass =
    variant === "compact" ? "" : "panel p-5";

  return (
    <section className={wrapperClass}>
      <div className="eyebrow">Lineage</div>
      <h2 className="section-title mt-4">{title}</h2>
      <p className="mt-3 text-sm leading-6 text-muted">{description}</p>
      <div className="mt-5 flex flex-wrap gap-2">
        {tables.length > 0 ? (
          tables.map((table) => (
            <span key={table} className="chip">
              {table}
            </span>
          ))
        ) : (
          <span className="text-sm leading-6 text-muted">
            Run a query to see the validated table lineage here.
          </span>
        )}
      </div>
    </section>
  );
}
