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
    <section className="panel-strong border-accent/20 p-4 md:p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="eyebrow">AskData chat</p>
          <h2 className="section-title mt-4">Ask a business question</h2>
        </div>
        <span className="chip">{isLoading ? "Thinking" : "Ready"}</span>
      </div>

      <label className="mt-4 block">
        <span className="mb-2 block text-sm font-semibold text-ink">Message</span>
        <textarea
          rows={4}
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          placeholder="Ask about revenue, customers, rentals, trends, or categories..."
          className="w-full resize-none rounded-[28px] border border-line bg-white px-4 py-4 text-sm leading-6 text-ink outline-none transition focus:border-accent"
        />
      </label>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onSubmit}
          disabled={isLoading || !question.trim()}
          className="min-h-11 cursor-pointer rounded-full bg-accent px-5 py-3 text-sm font-semibold text-white shadow-soft transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? "Thinking..." : "Send"}
        </button>
        <span className="text-sm leading-6 text-muted">
          AskData will answer in the conversation and keep the technical detail available only when you need it.
        </span>
      </div>
    </section>
  );
}
