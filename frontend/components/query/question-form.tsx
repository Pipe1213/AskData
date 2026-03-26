type QuestionFormProps = {
  question: string;
  isLoading: boolean;
  onQuestionChange: (value: string) => void;
  onSubmit: () => void;
};

export function QuestionForm({
  question,
  isLoading,
  onQuestionChange,
  onSubmit,
}: QuestionFormProps) {
  return (
    <section className="panel-strong p-5 md:p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Question input</p>
          <h2 className="section-title mt-4">What do you want to understand?</h2>
        </div>
        <span className="chip">{isLoading ? "Running" : "Live query"}</span>
      </div>

      <label className="mt-5 block">
        <span className="mb-2 block text-sm font-semibold text-ink">Business question</span>
        <textarea
          rows={6}
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          placeholder="Ask a business question about the Pagila dataset..."
          className="w-full resize-none rounded-[24px] border border-line bg-white px-4 py-4 text-sm leading-6 text-ink outline-none transition focus:border-accent"
        />
      </label>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onSubmit}
          disabled={isLoading || !question.trim()}
          className="rounded-full bg-accent px-5 py-3 text-sm font-semibold text-white shadow-soft transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? "Running..." : "Run query"}
        </button>
        <span className="text-sm leading-6 text-muted">
          The form sends the question to the live backend and fills the workspace below when the
          response returns.
        </span>
      </div>
    </section>
  );
}
