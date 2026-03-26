type ExamplePromptsProps = {
  prompts: string[];
  disabled?: boolean;
  onSelectPrompt?: (prompt: string) => void;
};

export function ExamplePrompts({
  prompts,
  disabled = false,
  onSelectPrompt,
}: ExamplePromptsProps) {
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

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            disabled={disabled}
            onClick={() => onSelectPrompt?.(prompt)}
            className="rounded-[24px] border border-line bg-white/80 px-4 py-4 text-left text-sm leading-6 text-ink transition hover:-translate-y-0.5 hover:border-accent hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {prompt}
          </button>
        ))}
      </div>
    </section>
  );
}
