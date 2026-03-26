type AnswerPanelProps = {
  question?: string;
  summary?: string;
  isLoading: boolean;
};

export function AnswerPanel({
  question,
  summary,
  isLoading,
}: AnswerPanelProps) {
  const displaySummary = isLoading
    ? "The backend is running the pipeline and will return a grounded answer summary when execution finishes."
    : summary ??
      "Run a query to see the backend’s answer summary here. This panel is meant to give the user a fast, human-readable explanation before they inspect the SQL or raw rows.";

  return (
    <section className="panel-strong p-5">
      <div className="eyebrow">Answer</div>
      <h3 className="section-title mt-4">Short answer summary</h3>
      {question ? (
        <p className="mt-3 text-sm leading-6 text-muted">
          <strong className="text-ink">Question:</strong> {question}
        </p>
      ) : null}
      <p className="mt-4 text-base leading-7 text-ink">
        {displaySummary}
      </p>
    </section>
  );
}
