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
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="eyebrow">AskData chat</p>
        <span className="chip">{isLoading ? "Thinking" : "Ready"}</span>
      </div>

      <label className="block">
        <textarea
          rows={3}
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          placeholder="Ask about revenue, customers, rentals, trends, or categories..."
          className="min-h-[112px] w-full resize-none rounded-[26px] border border-line bg-white px-4 py-4 text-sm leading-6 text-ink outline-none transition focus:border-accent"
        />
      </label>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm leading-6 text-muted">
          The answer appears in the conversation. Open details only when you need them.
        </span>
        <button
          type="button"
          onClick={onSubmit}
          disabled={isLoading || !question.trim()}
          className="min-h-11 cursor-pointer rounded-full bg-accent px-5 py-3 text-sm font-semibold text-white shadow-soft transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? "Thinking..." : "Send"}
        </button>
      </div>
    </section>
  );
}
