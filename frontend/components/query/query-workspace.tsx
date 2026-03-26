"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { ChartPanel } from "@/components/result/chart-panel";
import { ResultsTable } from "@/components/result/results-table";
import { SqlPanel } from "@/components/result/sql-panel";
import { UsedTablesPanel } from "@/components/result/used-tables-panel";
import { canRenderChart } from "@/lib/chart";
import type { ConversationTurn } from "@/lib/types";

type QueryWorkspaceProps = {
  turns: ConversationTurn[];
  isLoading: boolean;
};

export function QueryWorkspace({ turns, isLoading }: QueryWorkspaceProps) {
  const lastResolvedTurn = [...turns]
    .reverse()
    .find((turn) => turn.status === "success" || turn.status === "error");
  const conversationEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [turns.length, isLoading]);

  return (
    <section className="panel p-4 md:p-6">
      <div className="flex flex-col gap-3 border-b border-line pb-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="eyebrow">Conversation</p>
          <h2 className="section-title mt-4">AskData session</h2>
          <p className="section-copy mt-3">
            The answer comes first. SQL, rows, and other artifacts stay available without taking
            over the whole page.
          </p>
        </div>
        <span className="chip">
          {isLoading
            ? "Assistant is thinking"
            : lastResolvedTurn?.status === "success"
              ? "Latest answer ready"
              : lastResolvedTurn?.status === "error"
                ? "Last turn failed"
                : "Start the conversation"}
        </span>
      </div>

      <div className="mt-6 space-y-5">
        {turns.length === 0 && !isLoading ? (
          <AssistantFrame>
            <div className="space-y-4">
              <p className="text-sm font-semibold uppercase tracking-[0.16em] text-accent">
                Assistant
              </p>
              <h3 className="font-serif text-3xl leading-tight tracking-[-0.03em] text-ink">
                Ask a question in plain language. Inspect only the detail you need.
              </h3>
              <p className="max-w-[65ch] text-sm leading-7 text-muted md:text-base">
                AskData is tuned for business questions over the Pagila PostgreSQL dataset. Start
                with revenue, customers, rentals, trends, or categories. When the answer comes
                back, the supporting artifacts appear inside the response instead of taking over the
                page.
              </p>
            </div>
          </AssistantFrame>
        ) : null}

        {turns.map((turn) => (
          <div key={turn.id} className="space-y-4">
            <UserBubble>{turn.question}</UserBubble>

            {turn.status === "loading" ? <LoadingReply /> : null}
            {turn.status === "error" ? <ErrorReply warnings={turn.error.warnings} message={turn.error.error.message} /> : null}
            {turn.status === "success" ? <SuccessReply turn={turn} /> : null}
          </div>
        ))}

        <div ref={conversationEndRef} />
      </div>
    </section>
  );
}

type FrameProps = {
  children: ReactNode;
  tone?: "default" | "warning";
};

function AssistantFrame({ children, tone = "default" }: FrameProps) {
  return (
    <article
      className={`mr-auto max-w-[920px] rounded-[30px] border px-5 py-5 shadow-soft md:px-6 md:py-6 ${
        tone === "warning"
          ? "border-[#e6c3ad] bg-[#fff4ed]"
          : "border-line bg-white/88"
      }`}
    >
      {children}
    </article>
  );
}

function UserBubble({ children }: { children: string }) {
  return (
    <article className="ml-auto max-w-[820px] rounded-[28px] bg-accent px-5 py-4 text-sm leading-7 text-white shadow-soft md:px-6">
      {children}
    </article>
  );
}

function LoadingReply() {
  return (
    <AssistantFrame>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="typing-dot" />
          <span className="typing-dot animation-delay-150" />
          <span className="typing-dot animation-delay-300" />
        </div>
        <p className="text-sm leading-6 text-muted">
          AskData is retrieving schema context, generating SQL, validating it, and preparing the
          answer.
        </p>
      </div>
    </AssistantFrame>
  );
}

function ErrorReply({
  message,
  warnings,
}: {
  message: string;
  warnings: string[];
}) {
  return (
    <AssistantFrame tone="warning">
      <p className="text-sm font-semibold uppercase tracking-[0.16em] text-accent">
        Assistant
      </p>
      <h3 className="mt-4 text-xl font-semibold text-ink">
        I could not answer that cleanly
      </h3>
      <p className="mt-3 text-sm leading-7 text-muted md:text-base">
        {message}
      </p>
      {warnings.length > 0 ? (
        <div className="mt-5 flex flex-wrap gap-2">
          {warnings.map((warning, index) => (
            <span key={`${warning}-${index}`} className="chip">
              {warning}
            </span>
          ))}
        </div>
      ) : null}
    </AssistantFrame>
  );
}

function SuccessReply({
  turn,
}: {
  turn: Extract<ConversationTurn, { status: "success" }>;
}) {
  const queryResult = turn.response;
  const shouldShowChart =
    canRenderChart(queryResult.chart_recommendation) && queryResult.rows.length > 0;

  return (
    <AssistantFrame>
      <p className="text-sm font-semibold uppercase tracking-[0.16em] text-accent">
        Assistant
      </p>
      <div className="mt-4 space-y-4">
        <div className="space-y-3">
          <h3 className="font-serif text-[1.85rem] leading-tight tracking-[-0.03em] text-ink md:text-[2.2rem]">
            {queryResult.answer_summary}
          </h3>
          <div className="flex flex-wrap gap-2">
            <span className="chip">{queryResult.rows.length} rows</span>
            <span className="chip">{queryResult.columns.length} columns</span>
            <span className="chip">{queryResult.chart_recommendation.type}</span>
          </div>
        </div>

        {shouldShowChart ? (
          <ChartPanel
            chartRecommendation={queryResult.chart_recommendation}
            columns={queryResult.columns}
            rows={queryResult.rows}
            isLoading={false}
            variant="embedded"
          />
        ) : null}

        <div className="space-y-3">
          <details className="details-card">
            <summary>
              <span>Preview result rows</span>
              <span className="chip">table</span>
            </summary>
            <div className="details-body">
              <ResultsTable
                columns={queryResult.columns}
                rows={queryResult.rows}
                isLoading={false}
                variant="embedded"
              />
            </div>
          </details>

          <details className="details-card">
            <summary>
              <span>Inspect generated SQL</span>
              <span className="chip">optional</span>
            </summary>
            <div className="details-body">
              <SqlPanel
                sql={queryResult.generated_sql}
                isLoading={false}
                variant="embedded"
              />
            </div>
          </details>

          {queryResult.used_tables.length > 0 ? (
            <details className="details-card">
              <summary>
                <span>See used tables</span>
                <span className="chip">{queryResult.used_tables.length}</span>
              </summary>
              <div className="details-body">
                <UsedTablesPanel
                  title="Tables used for this answer"
                  description="These tables were reported by the backend after validation and execution."
                  tables={queryResult.used_tables}
                  variant="compact"
                />
              </div>
            </details>
          ) : null}
        </div>
      </div>
    </AssistantFrame>
  );
}
