const sampleSql = `SELECT c.name AS category, SUM(p.amount) AS revenue
FROM payment p
JOIN rental r ON r.rental_id = p.rental_id
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film_category fc ON fc.film_id = i.film_id
JOIN category c ON c.category_id = fc.category_id
GROUP BY c.name
ORDER BY revenue DESC
LIMIT 10;`;

type SqlPanelProps = {
  sql?: string;
  isLoading: boolean;
  variant?: "panel" | "embedded";
};

export function SqlPanel({ sql, isLoading, variant = "panel" }: SqlPanelProps) {
  const wrapperClass =
    variant === "embedded"
      ? "rounded-[24px] border border-line bg-[#171311] p-4"
      : "panel p-5";

  return (
    <section className={wrapperClass}>
      {variant === "panel" ? (
        <>
          <div className="eyebrow">SQL</div>
          <h3 className="section-title mt-4">Generated query</h3>
        </>
      ) : (
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#cdb7a8]">
            Generated SQL
          </p>
          <span className="text-xs text-[#cdb7a8]">{isLoading ? "pending" : "validated"}</span>
        </div>
      )}
      <pre className={`${variant === "panel" ? "mt-4 rounded-[24px] bg-[#171311] p-4" : ""} overflow-x-auto text-sm leading-6 text-[#f5eadc]`}>
        <code>
          {isLoading
            ? "-- Waiting for the backend to return validated SQL..."
            : sql ?? sampleSql}
        </code>
      </pre>
    </section>
  );
}
