import Link from "next/link";

export function AppHeader() {
  return (
    <header className="panel px-5 py-4 md:px-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <Link href="/" className="font-serif text-3xl tracking-[-0.04em] text-ink">
            AskData
          </Link>
          <p className="mt-1 max-w-[50ch] text-sm leading-6 text-muted">
            Natural-language analytics over PostgreSQL with safe SQL execution and inspectable results.
          </p>
        </div>

        <nav className="flex flex-wrap gap-2">
          <Link
            href="/"
            className="rounded-full border border-line bg-white/75 px-4 py-2 text-sm font-medium text-ink transition hover:border-accent hover:text-accent"
          >
            Chat
          </Link>
          <Link
            href="/schema"
            className="rounded-full border border-line bg-white/75 px-4 py-2 text-sm font-medium text-ink transition hover:border-accent hover:text-accent"
          >
            Schema
          </Link>
        </nav>
      </div>
    </header>
  );
}
