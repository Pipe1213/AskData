import Link from "next/link";

import { AppHeader } from "@/components/layout/app-header";
import { PageShell } from "@/components/layout/page-shell";
import { SchemaOverview } from "@/components/schema/schema-overview";

export default function SchemaPage() {
  return (
    <PageShell>
      <AppHeader />
      <main className="mt-6 space-y-6">
        <section className="panel bg-hero-wash p-6 md:p-8">
          <div className="eyebrow">Schema Overview</div>
          <div className="mt-4 flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
            <div className="max-w-[70ch]">
              <h1 className="font-serif text-4xl leading-[0.98] tracking-[-0.04em] text-ink md:text-5xl">
                Browse the tables behind the answers.
              </h1>
              <p className="mt-4 text-base leading-7 text-muted">
                This page now renders the live <code>/schema/overview</code> response from the
                backend. It gives the product a dedicated place for schema exploration instead of
                hiding that information inside the main query workspace.
              </p>
            </div>
            <Link
              href="/"
              className="inline-flex items-center justify-center rounded-full border border-line bg-white px-5 py-3 text-sm font-semibold text-ink transition hover:border-accent hover:text-accent"
            >
              Back to AskData
            </Link>
          </div>
        </section>

        <SchemaOverview />
      </main>
    </PageShell>
  );
}
