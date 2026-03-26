"use client";

import { useState } from "react";

import type { QueryResponse } from "@/lib/types";

import { AnswerPanel } from "@/components/result/answer-panel";
import { ChartPanel } from "@/components/result/chart-panel";
import { ResultsTable } from "@/components/result/results-table";
import { SqlPanel } from "@/components/result/sql-panel";

type QueryWorkspaceProps = {
  queryResult: QueryResponse | null;
  isLoading: boolean;
  hasError: boolean;
};

export function QueryWorkspace({
  queryResult,
  isLoading,
  hasError,
}: QueryWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("answer");
  const hasResult = Boolean(queryResult);
  const workspaceSummary = isLoading
    ? "Running the backend pipeline..."
    : hasResult
      ? `${queryResult?.rows.length ?? 0} rows, ${queryResult?.columns.length ?? 0} columns`
      : hasError
        ? "The last request failed."
        : "Run a question to populate this workspace.";

  return (
    <section className="panel p-5 md:p-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="eyebrow">Workspace</p>
          <h2 className="section-title mt-4">Results workspace</h2>
        </div>
        <span className="chip">{workspaceSummary}</span>
      </div>

      <div className="mt-6 space-y-5">
        <div className="flex flex-wrap gap-2">
          {workspaceTabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
                  isActive
                    ? "border-accent bg-accent text-white"
                    : "border-line bg-white/80 text-ink hover:border-accent hover:text-accent"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        {!hasResult && !isLoading ? (
          <section className="panel-strong p-6">
            <h3 className="section-title">No result yet</h3>
            <p className="mt-3 text-sm leading-6 text-muted">
              Use one of the prompts above or type your own question. When the backend responds,
              this workspace will switch from placeholder mode to the live answer.
            </p>
          </section>
        ) : null}

        {activeTab === "answer" ? (
          <AnswerPanel
            question={queryResult?.question}
            summary={queryResult?.answer_summary}
            isLoading={isLoading}
          />
        ) : null}

        {activeTab === "results" ? (
          <ResultsTable
            columns={queryResult?.columns}
            rows={queryResult?.rows}
            isLoading={isLoading}
          />
        ) : null}

        {activeTab === "chart" ? (
          <ChartPanel
            chartRecommendation={queryResult?.chart_recommendation}
            columns={queryResult?.columns}
            rows={queryResult?.rows}
            isLoading={isLoading}
          />
        ) : null}

        {activeTab === "sql" ? (
          <SqlPanel sql={queryResult?.generated_sql} isLoading={isLoading} />
        ) : null}
      </div>
    </section>
  );
}

type WorkspaceTab = "answer" | "results" | "chart" | "sql";

const workspaceTabs: Array<{ id: WorkspaceTab; label: string }> = [
  { id: "answer", label: "Answer" },
  { id: "results", label: "Results" },
  { id: "chart", label: "Chart" },
  { id: "sql", label: "SQL" },
];
