"use client";

import { useEffect, useState } from "react";

import { Sidebar } from "@/components/layout/sidebar";
import { QuestionForm } from "@/components/query/question-form";
import { QueryWorkspace } from "@/components/query/query-workspace";
import { SchemaOverview } from "@/components/schema/schema-overview";
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

type DashboardView = "chat" | "schema";

export function QueryDashboard() {
  const [activeView, setActiveView] = useState<DashboardView>("chat");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [examplePrompts, setExamplePrompts] = useState<string[]>(fallbackPrompts);

  useEffect(() => {
    let isActive = true;

    async function loadExamples() {
      try {
        const examples = await fetchExampleQuestions();
        if (!isActive) {
          return;
        }

        const questions = normalizeExamples(examples);
        if (questions.length > 0) {
          setExamplePrompts(questions);
        }
      } catch {
        if (!isActive) {
          return;
        }
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

  function handleNewChat() {
    if (isLoading) {
      return;
    }

    setActiveView("chat");
    setQuestion("");
    setTurns([]);
  }

  function handleSelectPrompt(prompt: string) {
    setActiveView("chat");
    setQuestion(prompt);
  }

  return (
    <main
      className={`grid h-[calc(100vh-2rem)] gap-4 md:h-[calc(100vh-2.5rem)] ${
        sidebarCollapsed
          ? "xl:grid-cols-[112px_minmax(0,1fr)]"
          : "xl:grid-cols-[320px_minmax(0,1fr)] 2xl:grid-cols-[340px_minmax(0,1fr)]"
      }`}
    >
      <Sidebar
        activeView={activeView}
        collapsed={sidebarCollapsed}
        onSelectView={setActiveView}
        onToggleCollapse={() => setSidebarCollapsed((current) => !current)}
        prompts={examplePrompts}
        onNewChat={handleNewChat}
        onSelectPrompt={handleSelectPrompt}
        warnings={latestWarnings}
        usedTables={latestUsedTables}
        isLoading={isLoading}
      />

      <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
        {activeView === "chat" ? (
          <>
            <div className="min-h-0 flex-1">
              <QueryWorkspace
                turns={turns}
                isLoading={isLoading}
              />
            </div>

            <div className="border-t border-line bg-white/88 px-4 py-4 backdrop-blur md:px-5">
              <QuestionForm
                question={question}
                isLoading={isLoading}
                onQuestionChange={setQuestion}
                onSubmit={handleSubmit}
              />
            </div>
          </>
        ) : (
          <SchemaOverview variant="embedded" />
        )}
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
