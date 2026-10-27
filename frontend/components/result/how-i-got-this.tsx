"use client";

import { useId, useState } from "react";

import { ChevronDownIcon, ChevronUpIcon } from "@/components/ui/icons";
import { formatSql, shortTableName } from "@/lib/format";
import type { QueryResponse } from "@/lib/types";

type HowIGotThisProps = {
  response: QueryResponse;
  durationMs?: number;
  onRunAgain?: () => void;
};

export function HowIGotThis({ response, durationMs, onRunAgain }: HowIGotThisProps) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const panelId = useId();

  const understoodAs = describeTask(response.plan?.task_type ?? response.trace?.task_type);
  const tables = response.used_tables.map(shortTableName);
  const retryCount = (response.trace?.retries.length ?? 0) + (response.repaired && !(response.trace?.retries.length) ? 1 : 0);
  const retryLine =
    retryCount === 0
      ? null
      : response.repaired
        ? `Retried ${retryCount === 1 ? "once" : `${retryCount} times`} after an error.`
        : `Retried ${retryCount === 1 ? "once" : `${retryCount} times`} before answering.`;
  const footer = [
    durationMs != null ? `${(durationMs / 1000).toFixed(1)} s` : null,
    response.usage?.cost_usd != null ? `$${response.usage.cost_usd.toFixed(4)}` : null,
  ].filter(Boolean);

  async function handleCopySql() {
    try {
      await navigator.clipboard.writeText(response.generated_sql);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="rounded-[14px] border border-line bg-surface">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
        className="flex min-h-[52px] w-full items-center justify-between px-4 text-left text-[15px] font-semibold text-ink md:px-5"
      >
        How I got this
        {open ? <ChevronUpIcon /> : <ChevronDownIcon />}
      </button>
      {open ? (
        <div id={panelId} className="flex flex-col gap-4 px-4 pb-5 text-sm leading-normal md:px-5">
          <dl className="m-0 grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-[140px_minmax(0,1fr)]">
            {understoodAs ? (
              <>
                <dt className="text-muted">Understood as</dt>
                <dd className="m-0">{understoodAs}</dd>
              </>
            ) : null}
            {tables.length > 0 ? (
              <>
                <dt className="text-muted">Tables</dt>
                <dd className="m-0">{tables.join(", ")}</dd>
              </>
            ) : null}
            <dt className="text-muted">Safety</dt>
            <dd className="m-0">Read-only query, checked before it ran.</dd>
            {retryLine ? (
              <>
                <dt className="text-muted">Retries</dt>
                <dd className="m-0">{retryLine}</dd>
              </>
            ) : null}
          </dl>
          {response.generated_sql ? (
            <div className="relative rounded-[10px] bg-code p-4 text-codeText">
              <button
                type="button"
                onClick={handleCopySql}
                className="absolute right-2 top-2 h-8 rounded-md border border-codeLine px-2.5 text-xs font-medium text-codeText hover:border-codeText"
              >
                {copied ? "Copied" : "Copy SQL"}
              </button>
              <pre className="m-0 whitespace-pre-wrap break-words pr-24 font-mono text-[13px] leading-relaxed">
                {formatSql(response.generated_sql)}
              </pre>
            </div>
          ) : null}
          {footer.length > 0 || onRunAgain ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted">
              {footer.length > 0 ? <span>{footer.join(" · ")}</span> : null}
              {onRunAgain ? (
                <button type="button" onClick={onRunAgain} className="text-link min-h-8">
                  Run again
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

const TASK_DESCRIPTIONS: Record<string, string> = {
  ranking: "A ranking: the rows with the highest values of the measure you asked about, highest first.",
  aggregation: "A total, count or average of the measure you asked about.",
  trend: "How the measure you asked about changes over time.",
  comparison: "The measure you asked about, side by side for each group.",
  follow_up_refinement: "A change to the previous answer, as you asked.",
  schema_lookup: "Which tables hold this kind of information.",
  lookup: "The records that match your question.",
};

function describeTask(taskType: string | undefined): string | null {
  return taskType ? (TASK_DESCRIPTIONS[taskType] ?? null) : null;
}
