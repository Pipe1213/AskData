import type { FormEvent } from "react";

import { ArrowUpIcon } from "@/components/ui/icons";

type QuestionFormProps = {
  question: string;
  isLoading: boolean;
  placeholder: string;
  helper?: string | null;
  onQuestionChange: (value: string) => void;
  onSubmit: () => void;
};

export function QuestionForm({
  question,
  isLoading,
  placeholder,
  helper,
  onQuestionChange,
  onSubmit,
}: QuestionFormProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <form onSubmit={handleSubmit} className="flex w-full max-w-conversation flex-col gap-2">
      <div className="flex items-center gap-2 rounded-[14px] border border-inputLine bg-surface py-1.5 pl-4 pr-1.5 focus-within:border-muted">
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <input
          id="question"
          type="text"
          autoComplete="off"
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          placeholder={placeholder}
          className="h-10 min-w-0 flex-1 border-0 bg-transparent text-base text-ink outline-none placeholder:text-muted focus-visible:outline-none"
        />
        <button
          type="submit"
          aria-label={isLoading ? "Working on the answer" : "Send"}
          disabled={isLoading || !question.trim()}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[10px] bg-accent text-white hover:bg-accentHover disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ArrowUpIcon size={18} />
        </button>
      </div>
      {helper ? <p className="text-center text-[13px] text-muted">{helper}</p> : null}
    </form>
  );
}
