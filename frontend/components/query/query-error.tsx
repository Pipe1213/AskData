type QueryErrorProps = {
  title: string;
  message: string;
  warnings?: string[];
  errorCode?: string;
};

export function QueryError({
  title,
  message,
  warnings = [],
  errorCode,
}: QueryErrorProps) {
  return (
    <section className="panel border-accent/20 bg-[#fff7f1] p-5">
      <div className="eyebrow">Request error</div>
      <h2 className="section-title mt-4">{title}</h2>
      <p className="mt-3 text-sm leading-6 text-muted">{message}</p>
      {errorCode ? (
        <p className="mt-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted">
          code: {errorCode}
        </p>
      ) : null}
      {warnings.length > 0 ? (
        <div className="mt-4 space-y-2">
          {warnings.map((warning) => (
            <div
              key={warning}
              className="rounded-2xl border border-line bg-white/80 px-4 py-3 text-sm leading-6 text-muted"
            >
              {warning}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
