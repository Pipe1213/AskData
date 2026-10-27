"use client";

import { useEffect, useRef } from "react";

import { HowIGotThis } from "@/components/result/how-i-got-this";
import { ResultCard } from "@/components/result/result-card";
import { AlertIcon, QuestionIcon } from "@/components/ui/icons";
import type { ConversationTurn, QueryResponse } from "@/lib/types";

type QueryWorkspaceProps = {
  turns: ConversationTurn[];
  busy: boolean;
  allowRunAgain: boolean;
  onAsk: (question: string) => void;
  onRunAgain: (turnId: string, question: string) => void;
  onDownloadCsv: (turn: Extract<ConversationTurn, { status: "success" }>) => void;
};

export function QueryWorkspace({
  turns,
  busy,
  allowRunAgain,
  onAsk,
  onRunAgain,
  onDownloadCsv,
}: QueryWorkspaceProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  return (
    <div className="flex w-full max-w-conversation flex-col gap-6" aria-live="polite">
      {turns.map((turn, index) => (
        <div key={turn.id} className="flex flex-col gap-6">
          {index > 0 ? <hr className="m-0 border-0 border-t border-line" /> : null}
          <p className="m-0 max-w-[80%] self-end rounded-[14px] bg-bubble px-4 py-3 text-[15px] leading-snug">
            {turn.question}
          </p>
          {turn.status === "loading" ? <LoadingReply /> : null}
          {turn.status === "error" ? <ErrorReply message={turn.error.error.message} /> : null}
          {turn.status === "success" ? (
            <Reply
              turn={turn}
              busy={busy}
              allowRunAgain={allowRunAgain}
              onAsk={onAsk}
              onRunAgain={onRunAgain}
              onDownloadCsv={onDownloadCsv}
            />
          ) : null}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}

function Reply({
  turn,
  busy,
  allowRunAgain,
  onAsk,
  onRunAgain,
  onDownloadCsv,
}: {
  turn: Extract<ConversationTurn, { status: "success" }>;
  busy: boolean;
  allowRunAgain: boolean;
  onAsk: (question: string) => void;
  onRunAgain: (turnId: string, question: string) => void;
  onDownloadCsv: (turn: Extract<ConversationTurn, { status: "success" }>) => void;
}) {
  const response = turn.response;

  if (response.response_type === "clarification" && response.clarification) {
    return <ClarificationReply clarification={response.clarification} busy={busy} onAsk={onAsk} />;
  }
  if (response.response_type === "cannot_answer" && response.cannot_answer) {
    return <CannotAnswerReply cannotAnswer={response.cannot_answer} busy={busy} onAsk={onAsk} />;
  }

  const assumptions = response.assumptions ?? [];
  const showCard = hasResultCard(response);

  return (
    <div className="flex flex-col gap-[18px]">
      <p className="m-0 text-lg font-medium leading-[1.45] md:text-xl">{response.answer_summary}</p>
      {assumptions.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13px] text-muted">I assumed:</span>
          {assumptions.map((assumption) => (
            <span key={assumption} className="rounded-full border border-line bg-surface px-2.5 py-1 text-[13px] leading-snug">
              {assumption}
            </span>
          ))}
        </div>
      ) : null}
      {showCard ? <ResultCard response={response} onDownloadCsv={() => onDownloadCsv(turn)} /> : null}
      {response.generated_sql ? (
        <HowIGotThis
          response={response}
          durationMs={turn.duration_ms}
          onRunAgain={allowRunAgain && !busy ? () => onRunAgain(turn.id, turn.question) : undefined}
        />
      ) : null}
    </div>
  );
}

/** Single values and empty results are fully said by the sentence. */
function hasResultCard(response: QueryResponse): boolean {
  if (response.row_count === 0 || response.rows.length === 0) {
    return false;
  }
  const singleValue = response.rows.length === 1 && response.columns.length <= 2;
  return !singleValue;
}

function ClarificationReply({
  clarification,
  busy,
  onAsk,
}: {
  clarification: { question: string; options: string[] };
  busy: boolean;
  onAsk: (question: string) => void;
}) {
  return (
    <div className="flex flex-col gap-3.5">
      <div className="section-label flex items-center gap-2 text-info">
        <QuestionIcon />
        Question before answering
      </div>
      <p className="m-0 text-lg leading-normal">{clarification.question}</p>
      <div className="flex flex-wrap gap-2">
        {clarification.options.map((option) => (
          <button
            key={option}
            type="button"
            disabled={busy}
            onClick={() => onAsk(option)}
            className="min-h-11 rounded-[10px] border border-info bg-surface px-4 py-2 text-left text-sm font-medium text-info hover:bg-infoBg disabled:cursor-not-allowed disabled:opacity-60"
          >
            {option}
          </button>
        ))}
      </div>
      <p className="m-0 text-[13px] text-muted">Or type what you mean below.</p>
    </div>
  );
}

function CannotAnswerReply({
  cannotAnswer,
  busy,
  onAsk,
}: {
  cannotAnswer: { reason: string; alternatives: string[] };
  busy: boolean;
  onAsk: (question: string) => void;
}) {
  const reason = cannotAnswer.reason
    .trim()
    .replace(/,?\s*so I didn['’]t run a query\.?$/i, "")
    .replace(/[.\s]+$/, "");

  return (
    <div className="flex flex-col gap-3.5">
      <div className="section-label flex items-center gap-2 text-warn">
        <AlertIcon />
        The data can&apos;t answer this
      </div>
      <p className="m-0 text-lg leading-normal">{reason}, so I didn&apos;t run a query.</p>
      {cannotAnswer.alternatives.length > 0 ? (
        <div className="flex flex-col gap-2">
          <span className="text-sm text-muted">I can answer instead:</span>
          <div className="flex flex-wrap gap-2">
            {cannotAnswer.alternatives.map((alternative) => (
              <button
                key={alternative}
                type="button"
                disabled={busy}
                onClick={() => onAsk(alternative)}
                className="min-h-11 rounded-[10px] border border-inputLine bg-surface px-4 py-2 text-left text-sm font-medium text-ink hover:border-muted disabled:cursor-not-allowed disabled:opacity-60"
              >
                {alternative}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function LoadingReply() {
  return (
    <div className="flex items-center gap-3 text-sm text-muted" role="status">
      <span className="flex items-center gap-1.5" aria-hidden="true">
        <span className="typing-dot" />
        <span className="typing-dot animation-delay-150" />
        <span className="typing-dot animation-delay-300" />
      </span>
      Reading the data…
    </div>
  );
}

function ErrorReply({ message }: { message: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-[14px] border border-dangerLine bg-dangerBg px-4 py-3 md:px-5">
      <div className="section-label flex items-center gap-2 text-danger">
        <AlertIcon />
        Something went wrong
      </div>
      <p className="m-0 text-[15px] leading-normal text-ink">{message}</p>
    </div>
  );
}
