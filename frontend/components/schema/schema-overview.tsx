"use client";

import { useEffect, useMemo, useState } from "react";

import { ChevronDownIcon, ChevronUpIcon } from "@/components/ui/icons";
import { fetchSchemaOverview } from "@/lib/api";
import type { SchemaOverviewResponse, SchemaTableSummary } from "@/lib/types";

type SchemaOverviewProps = {
  targetName: string;
};

/** Loads once per mount; the parent remounts it (via `key`) when the data source changes. */
export function SchemaOverview({ targetName }: SchemaOverviewProps) {
  const [overview, setOverview] = useState<SchemaOverviewResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let isActive = true;
    fetchSchemaOverview()
      .then((response) => {
        if (isActive) {
          setOverview(response);
        }
      })
      .catch((error: unknown) => {
        if (isActive) {
          setErrorMessage(error instanceof Error ? error.message : "The tables could not be loaded.");
        }
      });
    return () => {
      isActive = false;
    };
  }, []);

  const tables = useMemo(() => {
    const all = overview?.tables ?? [];
    const term = search.trim().toLowerCase();
    if (!term) {
      return all;
    }
    return all.filter((table) =>
      [table.name, table.description ?? "", ...table.columns.map((column) => column.name)]
        .join(" ")
        .toLowerCase()
        .includes(term),
    );
  }, [overview, search]);

  const showSchemaNames = new Set((overview?.tables ?? []).map((table) => table.schema)).size > 1;

  return (
    <div className="flex w-full max-w-conversation flex-col gap-5">
      <div className="flex flex-col gap-2">
        <h1 className="m-0 text-[28px] font-semibold tracking-[-0.02em]">Tables in {targetName}</h1>
        {overview ? (
          <p className="m-0 text-[15px] text-muted">
            {overview.tables.length} tables. Open one to see its columns and links to other tables.
          </p>
        ) : null}
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="table-search" className="text-sm font-medium">
          Search tables and columns
        </label>
        <input
          id="table-search"
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="h-11 w-full rounded-[10px] border border-inputLine bg-surface px-3 text-sm text-ink"
        />
      </div>

      {errorMessage ? <p className="m-0 text-sm text-danger">{errorMessage}</p> : null}
      {!overview && !errorMessage ? <p className="m-0 text-sm text-muted">Loading tables…</p> : null}
      {overview && tables.length === 0 ? (
        <p className="m-0 text-sm text-muted">No table or column matches “{search.trim()}”.</p>
      ) : null}

      {tables.length > 0 ? (
        <ul className="m-0 flex list-none flex-col overflow-hidden rounded-[14px] border border-line bg-surface p-0">
          {tables.map((table) => (
            <SchemaRow key={`${table.schema}.${table.name}`} table={table} showSchema={showSchemaNames} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function SchemaRow({ table, showSchema }: { table: SchemaTableSummary; showSchema: boolean }) {
  const [open, setOpen] = useState(false);
  const panelId = `table-${table.schema}-${table.name}`;
  const foreignKeyByColumn = new Map(
    table.foreign_keys.flatMap((key) =>
      key.columns.map((column, index) => [
        column,
        `${key.references_table}.${key.references_columns[index] ?? key.references_columns[0] ?? ""}`,
      ]),
    ),
  );

  return (
    <li className="border-b border-line last:border-b-0">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
        className="flex min-h-[52px] w-full items-center gap-3 px-4 py-2 text-left hover:bg-ground"
      >
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="font-mono text-sm font-medium text-ink">
            {showSchema ? `${table.schema}.` : ""}
            {table.name}
          </span>
          {table.description ? <span className="truncate text-[13px] text-muted">{table.description}</span> : null}
        </span>
        <span className="shrink-0 text-[13px] text-muted">
          {table.columns.length} {table.columns.length === 1 ? "column" : "columns"}
        </span>
        {open ? <ChevronUpIcon /> : <ChevronDownIcon />}
      </button>
      {open ? (
        <div id={panelId} className="px-4 pb-4">
          <table className="w-full border-collapse text-[13px]">
            <thead className="sr-only">
              <tr>
                <th scope="col">Column</th>
                <th scope="col">Type</th>
                <th scope="col">Links to</th>
              </tr>
            </thead>
            <tbody>
              {table.columns.map((column) => (
                <tr key={column.name} className="border-t border-line align-top">
                  <td className="py-1.5 pr-3 font-mono text-ink">{column.name}</td>
                  <td className="py-1.5 pr-3 text-muted">{column.data_type}</td>
                  <td className="py-1.5 text-muted">
                    {foreignKeyByColumn.has(column.name) ? `→ ${foreignKeyByColumn.get(column.name)}` : ""}
                    {column.description ? (
                      <span className="block text-inkSoft">{column.description}</span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </li>
  );
}
