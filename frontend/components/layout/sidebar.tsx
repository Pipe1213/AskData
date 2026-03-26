import Link from "next/link";

import { ExamplePrompts } from "@/components/query/example-prompts";
import { UsedTablesPanel } from "@/components/result/used-tables-panel";

type SidebarProps = {
  prompts: string[];
  onSelectPrompt: (prompt: string) => void;
  warnings: string[];
  usedTables: string[];
  isLoading: boolean;
};

export function Sidebar({
  prompts,
  onSelectPrompt,
  warnings,
  usedTables,
  isLoading,
}: SidebarProps) {
  const displayedWarnings =
    warnings.length > 0
      ? warnings
      : [
          isLoading
            ? "The backend is currently processing the question."
            : "Warnings appear here only when the backend has something important to surface.",
        ];

  return (
    <aside className="space-y-6 xl:sticky xl:top-8 xl:self-start">
      <section className="panel p-5">
        <div className="eyebrow">AskData</div>
        <h2 className="section-title mt-4">Conversation guide</h2>
        <p className="section-copy mt-3">
          Use the central conversation to ask questions. Keep this rail for prompt starters, schema
          access, and the latest response context.
        </p>
        <div className="mt-5 rounded-[22px] border border-line bg-white/75 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">Status</p>
          <p className="mt-2 text-sm font-semibold text-ink">
            {isLoading ? "Assistant is preparing a response" : "Ready for the next question"}
          </p>
        </div>
      </section>

      <section className="panel p-5">
        <ExamplePrompts
          prompts={prompts}
          disabled={isLoading}
          onSelectPrompt={onSelectPrompt}
          variant="compact"
        />
      </section>

      <section className="panel p-5">
        <div className="eyebrow">Warnings</div>
        <h2 className="section-title mt-4">Things to notice</h2>
        <p className="section-copy mt-3">
          If the backend repaired a query, used a proxy, or found ambiguity, it appears here.
        </p>
        <div className="mt-5 space-y-3">
          {displayedWarnings.map((warning, index) => (
            <div
              key={`${warning}-${index}`}
              className="rounded-3xl border border-line bg-white/70 px-4 py-3 text-sm leading-6 text-muted"
            >
              {warning}
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <div className="eyebrow">Schema access</div>
        <h2 className="section-title mt-4">Need more context?</h2>
        <p className="section-copy mt-3">
          Open the schema page to inspect tables, columns, and relationships before asking a more specific follow-up.
        </p>
        <Link
          href="/schema"
          className="mt-5 inline-flex min-h-11 items-center rounded-full border border-accent bg-accentSoft px-4 py-2 text-sm font-semibold text-accent transition hover:brightness-105"
        >
          Open schema overview
        </Link>
      </section>

      <UsedTablesPanel
        title="Latest used tables"
        description="These are the real tables reported by the backend after validation and execution."
        tables={usedTables}
        variant="compact"
      />
    </aside>
  );
}
