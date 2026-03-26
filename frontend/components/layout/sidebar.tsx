import Link from "next/link";

import { UsedTablesPanel } from "@/components/result/used-tables-panel";

type SidebarProps = {
  warnings: string[];
  usedTables: string[];
  isLoading: boolean;
};

export function Sidebar({ warnings, usedTables, isLoading }: SidebarProps) {
  const displayedWarnings =
    warnings.length > 0
      ? warnings
      : [
          isLoading
            ? "The backend is currently processing the question."
            : "Warnings appear here only when the backend has something important to surface.",
        ];

  return (
    <aside className="space-y-6">
      <section className="panel p-5">
        <div className="eyebrow">Query details</div>
        <h2 className="section-title mt-4">Helpful context</h2>
        <p className="section-copy mt-3">
          This side panel is only shown when the current state adds something useful: processing
          status, warnings, used tables, or schema access.
        </p>
        <div className="mt-5 rounded-[22px] border border-line bg-white/75 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">Status</p>
          <p className="mt-2 text-sm font-semibold text-ink">
            {isLoading ? "Running backend pipeline" : "Ready"}
          </p>
        </div>
      </section>

      <section className="panel p-5">
        <div className="eyebrow">Warnings</div>
        <h2 className="section-title mt-4">Things to notice</h2>
        <p className="section-copy mt-3">
          If the backend had to use a proxy, repair a query, or surface ambiguity, it appears here.
        </p>
        <div className="mt-5 space-y-3">
          {displayedWarnings.map((warning) => (
            <div
              key={`${warning}-${displayedWarnings.indexOf(warning)}`}
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
          Open the schema page to inspect tables, columns, and foreign key relationships.
        </p>
        <Link
          href="/schema"
          className="mt-5 inline-flex items-center rounded-full border border-accent bg-accentSoft px-4 py-2 text-sm font-semibold text-accent transition hover:brightness-105"
        >
          Open schema overview
        </Link>
      </section>

      <UsedTablesPanel
        title="Used tables"
        description="These are the real tables reported by the backend after validation and execution."
        tables={usedTables}
      />
    </aside>
  );
}
