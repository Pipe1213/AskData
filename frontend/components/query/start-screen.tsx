import type { DatasetCopy } from "@/lib/datasets";

type StartScreenProps = {
  copy: DatasetCopy;
  disabled: boolean;
  onAsk: (question: string) => void;
};

export function StartScreen({ copy, disabled, onAsk }: StartScreenProps) {
  return (
    <div className="flex w-full max-w-conversation flex-col gap-7">
      <div className="flex flex-col gap-2.5">
        <h1 className="m-0 text-[28px] font-semibold leading-tight tracking-[-0.02em] md:text-[32px]">
          {copy.heading}
        </h1>
        <p className="m-0 text-base leading-normal text-muted">{copy.description}</p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {copy.examples.map((example) => (
          <button
            key={example.question}
            type="button"
            disabled={disabled}
            onClick={() => onAsk(example.question)}
            className={`flex flex-col items-start gap-1.5 rounded-xl p-4 text-left disabled:cursor-not-allowed disabled:opacity-60 ${
              example.vague
                ? "border border-dashed border-accentDash bg-accentSoft hover:border-accent"
                : "border border-line bg-surface hover:border-inputLine"
            }`}
          >
            <span className={`section-label ${example.vague ? "text-accent" : ""}`}>{example.kind}</span>
            <span className="text-[15px] leading-snug text-ink">{example.question}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
