import type { ExamplePromptGroup } from "@/lib/types";

type ExamplePromptsProps = {
  groups: ExamplePromptGroup[];
  disabled?: boolean;
  onSelectPrompt?: (prompt: string) => void;
  variant?: "panel" | "compact";
};

export function ExamplePrompts({
  groups,
  disabled = false,
  onSelectPrompt,
  variant = "panel",
}: ExamplePromptsProps) {
  if (variant === "compact") {
    return (
      <section className="space-y-3">
        <div>
          <p className="eyebrow">Quick starts</p>
          <h2 className="section-title mt-4">Try one of these</h2>
          <p className="section-copy mt-3">
            These fill the chat composer with a real example question.
          </p>
        </div>

        {groups.map((group) => (
          <div key={group.title} className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">
              {group.title}
            </p>
            <div className="space-y-2">
              {group.prompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={disabled}
                  onClick={() => onSelectPrompt?.(prompt)}
                  className="flex min-h-11 w-full cursor-pointer items-start rounded-[20px] border border-line bg-white/85 px-4 py-3 text-left text-sm leading-6 text-ink transition hover:border-accent hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ))}
      </section>
    );
  }

  return (
    <section className="panel p-5 md:p-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="eyebrow">Example prompts</p>
          <h2 className="section-title mt-4">Prompt starters for the first product pass</h2>
        </div>
        <p className="section-copy max-w-[44ch]">
          These prompts feed the live query form. When the backend examples endpoint is available,
          the dashboard upgrades from local fallback prompts to the real curated list automatically.
        </p>
      </div>

      <div className="mt-5 space-y-5">
        {groups.map((group) => (
          <div key={group.title}>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">
              {group.title}
            </p>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {group.prompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={disabled}
                  onClick={() => onSelectPrompt?.(prompt)}
                  className="cursor-pointer rounded-[24px] border border-line bg-white/80 px-4 py-4 text-left text-sm leading-6 text-ink transition hover:-translate-y-0.5 hover:border-accent hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
