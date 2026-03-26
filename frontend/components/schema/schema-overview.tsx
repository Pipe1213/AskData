"use client";

import { useEffect, useMemo, useState } from "react";

import { SchemaTableList } from "@/components/schema/schema-table-list";
import { fetchSchemaOverview } from "@/lib/api";
import type { SchemaOverviewResponse } from "@/lib/types";

type LoadState = "idle" | "loading" | "success" | "error";

export function SchemaOverview() {
  const [schemaOverview, setSchemaOverview] = useState<SchemaOverviewResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let isActive = true;

    async function loadSchemaOverview() {
      setLoadState("loading");
      setErrorMessage(null);

      try {
        const response = await fetchSchemaOverview();
        if (!isActive) {
          return;
        }

        setSchemaOverview(response);
        setLoadState("success");
      } catch (error) {
        if (!isActive) {
          return;
        }

        setLoadState("error");
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Failed to load the schema overview from the backend.",
        );
      }
    }

    void loadSchemaOverview();

    return () => {
      isActive = false;
    };
  }, []);

  const filteredTables = useMemo(() => {
    const tables = schemaOverview?.tables ?? [];
    const normalizedSearch = search.trim().toLowerCase();

    if (!normalizedSearch) {
      return tables;
    }

    return tables.filter((table) => {
      const haystack = [
        table.name,
        table.schema_name,
        table.description ?? "",
        ...table.columns.map((column) => column.name),
      ]
        .join(" ")
        .toLowerCase();

      return haystack.includes(normalizedSearch);
    });
  }, [schemaOverview, search]);

  return (
    <div className="space-y-6">
      <section className="panel p-5 md:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="eyebrow">Live backend data</div>
            <h2 className="section-title mt-4">Search the Pagila schema</h2>
            <p className="mt-3 text-sm leading-6 text-muted">
              This page is now reading the real <code>/schema/overview</code> payload from the
              backend. Use search to narrow tables by name, description, or column names.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3 lg:w-[420px]">
            <Metric label="State" value={loadState} />
            <Metric
              label="Tables"
              value={String(schemaOverview?.tables.length ?? 0)}
            />
            <Metric
              label="Visible"
              value={String(filteredTables.length)}
            />
          </div>
        </div>

        <div className="mt-5">
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink">Search tables</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="payment, rental, customer, amount..."
              className="w-full rounded-[22px] border border-line bg-white px-4 py-3 text-sm leading-6 text-ink outline-none transition focus:border-accent"
            />
          </label>
        </div>
      </section>

      {loadState === "loading" ? (
        <section className="panel p-6">
          <p className="text-sm leading-6 text-muted">
            Loading schema metadata from the backend...
          </p>
        </section>
      ) : null}

      {loadState === "error" ? (
        <section className="panel p-6">
          <div className="eyebrow">Schema error</div>
          <h2 className="section-title mt-4">The schema overview could not be loaded</h2>
          <p className="mt-3 text-sm leading-6 text-muted">
            {errorMessage ?? "An unexpected schema-loading error occurred."}
          </p>
        </section>
      ) : null}

      {loadState === "success" && filteredTables.length === 0 ? (
        <section className="panel p-6">
          <div className="eyebrow">No matches</div>
          <h2 className="section-title mt-4">No tables matched your search</h2>
          <p className="mt-3 text-sm leading-6 text-muted">
            Try a broader search term like <code>payment</code>, <code>customer</code>, or
            <code> rental</code>.
          </p>
        </section>
      ) : null}

      {filteredTables.length > 0 ? <SchemaTableList tables={filteredTables} /> : null}
    </div>
  );
}

type MetricProps = {
  label: string;
  value: string;
};

function Metric({ label, value }: MetricProps) {
  return (
    <div className="rounded-[22px] border border-line bg-white/80 px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted">{label}</p>
      <p className="mt-2 text-sm font-semibold text-ink">{value}</p>
    </div>
  );
}
