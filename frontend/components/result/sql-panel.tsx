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
};

export function SqlPanel({ sql, isLoading }: SqlPanelProps) {
  return (
    <section className="panel p-5">
      <div className="eyebrow">SQL</div>
      <h3 className="section-title mt-4">Generated query</h3>
      <pre className="mt-4 overflow-x-auto rounded-[24px] bg-[#171311] p-4 text-sm leading-6 text-[#f5eadc]">
        <code>
          {isLoading
            ? "-- Waiting for the backend to return validated SQL..."
            : sql ?? sampleSql}
        </code>
      </pre>
    </section>
  );
}
