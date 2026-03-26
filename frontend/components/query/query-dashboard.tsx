"use client";

import { useEffect, useState } from "react";

import { Sidebar } from "@/components/layout/sidebar";
import { QuestionForm } from "@/components/query/question-form";
import { QueryWorkspace } from "@/components/query/query-workspace";
import { ApiError, fetchExampleQuestions, queryAskData } from "@/lib/api";
import type {
  ConversationMessage,
  ConversationTurn,
  ExampleQuestion,
  QueryErrorResponse,
} from "@/lib/types";

const fallbackPrompts = [
  "What are the top 10 film categories by total revenue?",
  "Which customers spent the most in total?",
  "How much revenue did each staff member process?",
  "What is the monthly trend of rentals this year?",
];

export function QueryDashboard() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [examplePrompts, setExamplePrompts] = useState<string[]>(fallbackPrompts);
  const [examplesState, setExamplesState] = useState<"idle" | "loading" | "success" | "error">("idle");

  useEffect(() => {
    let isActive = true;

    async function loadExamples() {
      setExamplesState("loading");

      try {
        const examples = await fetchExampleQuestions();
        if (!isActive) {
          return;
        }

        const questions = normalizeExamples(examples);
        if (questions.length > 0) {
          setExamplePrompts(questions);
        }
        setExamplesState("success");
      } catch {
        if (!isActive) {
          return;
        }

        setExamplesState("error");
      }
    }

    void loadExamples();

    return () => {
      isActive = false;
    };
  }, []);

  async function handleSubmit() {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || isLoading) {
      return;
    }

    const turnId = createTurnId();

    setIsLoading(true);
    setQuestion("");
    setTurns((currentTurns) => [
      ...currentTurns,
      {
        id: turnId,
        question: trimmedQuestion,
        status: "loading",
      },
    ]);

    try {
      const result = await queryAskData({
        question: trimmedQuestion,
        conversation_context: buildConversationContext(turns),
      });
      setTurns((currentTurns) =>
        currentTurns.map((turn) =>
          turn.id === turnId
            ? {
                id: turn.id,
                question: turn.question,
                status: "success",
                response: result,
              }
            : turn,
        ),
      );
    } catch (error) {
      const normalizedError = normalizeQueryError(error);
      setTurns((currentTurns) =>
        currentTurns.map((turn) =>
          turn.id === turnId
            ? {
                id: turn.id,
                question: turn.question,
                status: "error",
                error: normalizedError,
              }
            : turn,
        ),
      );
    } finally {
      setIsLoading(false);
    }
  }

  const latestResolvedTurn = [...turns]
    .reverse()
    .find((turn) => turn.status === "success" || turn.status === "error");
  const latestWarnings =
    latestResolvedTurn?.status === "success"
      ? latestResolvedTurn.response.warnings
      : latestResolvedTurn?.status === "error"
        ? latestResolvedTurn.error.warnings
        : [];
  const latestUsedTables =
    latestResolvedTurn?.status === "success" ? latestResolvedTurn.response.used_tables : [];

  return (
    <main className="mt-6 grid gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
      <Sidebar
        prompts={examplePrompts}
        onSelectPrompt={setQuestion}
        warnings={latestWarnings}
        usedTables={latestUsedTables}
        isLoading={isLoading}
      />

      <section className="space-y-5">
        <div className="panel bg-hero-wash p-6 md:p-8">
          <div className="max-w-[72ch]">
            <div className="eyebrow">AskData</div>
            <h1 className="mt-4 max-w-[14ch] font-serif text-4xl leading-[0.95] tracking-[-0.04em] text-ink md:text-6xl">
              Conversation first. Analysis when you need it.
            </h1>
            <p className="mt-5 max-w-[60ch] text-base leading-7 text-muted md:text-lg">
              Ask business questions in plain language and inspect the supporting SQL, rows, and
              chart only when they are useful.
            </p>
            <p className="mt-5 text-sm leading-6 text-muted">
              {examplesState === "success"
                ? "The left rail is using example prompts loaded from the backend."
                : examplesState === "loading"
                  ? "Loading curated example prompts from the backend..."
                  : "The left rail is using local fallback prompts until the backend examples finish loading."}
            </p>
          </div>
        </div>

        <QueryWorkspace
          turns={turns}
          isLoading={isLoading}
        />

        <div className="sticky bottom-4 z-20">
          <QuestionForm
            question={question}
            isLoading={isLoading}
            onQuestionChange={setQuestion}
            onSubmit={handleSubmit}
          />
        </div>
      </section>
    </main>
  );
}

function normalizeQueryError(error: unknown): QueryErrorResponse {
  if (error instanceof ApiError) {
    return error.payload;
  }

  if (isQueryErrorResponse(error)) {
    return error;
  }

  if (error instanceof Error) {
    return {
      error: {
        code: "frontend_error",
        message: error.message,
        details: {},
      },
      warnings: [],
    };
  }

  return {
    error: {
      code: "frontend_error",
      message: "An unexpected frontend error occurred.",
      details: {},
    },
    warnings: [],
  };
}

function isQueryErrorResponse(error: unknown): error is QueryErrorResponse {
  if (!error || typeof error !== "object") {
    return false;
  }

  const candidate = error as QueryErrorResponse;
  return (
    typeof candidate.error?.code === "string" &&
    typeof candidate.error?.message === "string" &&
    Array.isArray(candidate.warnings)
  );
}

function normalizeExamples(examples: ExampleQuestion[]): string[] {
  return examples
    .map((example) => example.question.trim())
    .filter((question) => question.length > 0);
}

function createTurnId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function buildConversationContext(turns: ConversationTurn[]): ConversationMessage[] {
  const resolvedTurns = turns.filter((turn) => turn.status === "success");
  const recentTurns = resolvedTurns.slice(-3);

  return recentTurns.flatMap((turn) => [
    {
      role: "user",
      content: turn.question,
    },
    {
      role: "assistant",
      content: turn.response.answer_summary,
    },
  ]);
}
