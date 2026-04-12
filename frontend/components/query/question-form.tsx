import { useEffect, useRef } from "react";

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
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = "0px";
    const nextHeight = Math.min(Math.max(textarea.scrollHeight, 52), 156);
    textarea.style.height = `${nextHeight}px`;
  }, [question]);

  return (
    <section>
      <div className="flex items-end gap-3">
        <label className="block flex-1">
          <textarea
            ref={textareaRef}
            rows={1}
            value={question}
            onChange={(event) => onQuestionChange(event.target.value)}
            placeholder="Ask about revenue, customers, rentals, trends, or categories..."
            className="max-h-[156px] min-h-[52px] w-full resize-none rounded-[24px] border border-line bg-white px-4 py-[13px] text-sm leading-6 text-ink outline-none transition focus:border-accent"
          />
        </label>
        <button
          type="button"
          onClick={onSubmit}
          disabled={isLoading || !question.trim()}
          className="min-h-[52px] shrink-0 cursor-pointer rounded-full bg-accent px-5 py-3 text-sm font-semibold text-white shadow-soft transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? "Thinking..." : "Send"}
        </button>
      </div>
    </section>
  );
}
