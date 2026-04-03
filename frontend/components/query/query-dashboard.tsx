"use client";

import { useEffect, useState } from "react";

import { Sidebar } from "@/components/layout/sidebar";
import { QuestionForm } from "@/components/query/question-form";
import { QueryWorkspace } from "@/components/query/query-workspace";
import { SchemaOverview } from "@/components/schema/schema-overview";
import {
  ApiError,
  exportSessionTurnCsv,
  fetchExampleQuestions,
  fetchSessionDetail,
  fetchSessions,
  queryAskData,
  renameSession,
  rerunSessionTurn,
} from "@/lib/api";
import type {
  ConversationMessage,
  ConversationTurn,
  ExamplePromptGroup,
  ExampleQuestion,
  QueryErrorResponse,
  SessionDetail,
  SessionSummary,
} from "@/lib/types";

const fallbackPrompts = [
  "What are the top 10 film categories by total revenue?",
  "Which customers spent the most in total?",
  "How much revenue did each staff member process?",
  "What is the monthly trend of rentals this year?",
  "Now show only the top 5",
];

type DashboardView = "chat" | "schema";

export function QueryDashboard() {
  const [activeView, setActiveView] = useState<DashboardView>("chat");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [examplePromptGroups, setExamplePromptGroups] = useState<ExamplePromptGroup[]>(
    groupExamples(fallbackPrompts),
  );

  useEffect(() => {
    let isActive = true;

    async function loadInitialState() {
      try {
        const [examples, sessionSummaries] = await Promise.all([
          fetchExampleQuestions().catch(() => [] as ExampleQuestion[]),
          fetchSessions().catch(() => [] as SessionSummary[]),
        ]);
        if (!isActive) {
          return;
        }

        const questions = normalizeExamples(examples);
        if (questions.length > 0) {
          setExamplePromptGroups(groupExamples(questions));
        }
        setSessions(sessionSummaries);
      } catch {
        if (!isActive) {
          return;
        }
      }
    }

    void loadInitialState();

    return () => {
      isActive = false;
    };
  }, []);

  async function handleSubmit() {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || isLoading) {
      return;
    }

    const localTurnId = createTurnId();
    const conversationContext = buildConversationContext(turns);

    setActiveView("chat");
    setIsLoading(true);
    setQuestion("");
    setTurns((currentTurns) => [
      ...currentTurns,
      {
        id: localTurnId,
        question: trimmedQuestion,
        status: "loading",
      },
    ]);

    try {
      const result = await queryAskData({
        question: trimmedQuestion,
        session_id: activeSessionId,
        conversation_context: conversationContext,
      });
      setTurns((currentTurns) =>
        currentTurns.map((turn) =>
          turn.id === localTurnId
            ? {
                id: result.turn_id ?? turn.id,
                question: turn.question,
                status: "success",
                response: result,
                created_at: result.created_at,
              }
            : turn,
        ),
      );
      if (result.session_id) {
        setActiveSessionId(result.session_id);
      }
      if (result.persisted) {
        void refreshSessions();
      }
    } catch (error) {
      const normalizedError = normalizeQueryError(error);
      setTurns((currentTurns) =>
        currentTurns.map((turn) =>
          turn.id === localTurnId
            ? {
                id: normalizedError.turn_id ?? turn.id,
                question: turn.question,
                status: "error",
                error: normalizedError,
                created_at: normalizedError.created_at,
              }
            : turn,
        ),
      );
      if (normalizedError.session_id) {
        setActiveSessionId(normalizedError.session_id);
      }
      if (normalizedError.persisted) {
        void refreshSessions();
      }
    } finally {
      setIsLoading(false);
    }
  }

  async function refreshSessions() {
    try {
      const sessionSummaries = await fetchSessions();
      setSessions(sessionSummaries);
    } catch {
      // Keep the last known sidebar state if the history refresh fails.
    }
  }

  async function handleSelectSession(sessionId: string) {
    if (isLoading) {
      return;
    }

    try {
      const session = await fetchSessionDetail(sessionId);
      setActiveView("chat");
      setActiveSessionId(session.id);
      setQuestion("");
      setTurns(mapSessionDetailToTurns(session));
    } catch {
      // Ignore failed restores and keep the current chat state.
    }
  }

  function handleNewChat() {
    if (isLoading) {
      return;
    }

    setActiveView("chat");
    setActiveSessionId(null);
    setQuestion("");
    setTurns([]);
  }

  function handleSelectPrompt(prompt: string) {
    setActiveView("chat");
    setQuestion(prompt);
  }

  async function handleRenameSession() {
    if (!activeSessionId) {
      return;
    }

    const activeSession = sessions.find((session) => session.id === activeSessionId);
    const nextTitle = window.prompt("Rename this session", activeSession?.title ?? "");
    if (nextTitle == null) {
      return;
    }

    const normalizedTitle = nextTitle.trim();
    if (!normalizedTitle) {
      return;
    }

    try {
      const updatedSession = await renameSession(activeSessionId, normalizedTitle);
      setSessions((currentSessions) =>
        currentSessions.map((session) =>
          session.id === updatedSession.id
            ? {
                ...session,
                title: updatedSession.title,
                updated_at: updatedSession.updated_at,
              }
            : session,
        ),
      );
    } catch {
      // Keep the existing title if the rename fails.
    }
  }

  async function handleRerunTurn(turnId: string, originalQuestion: string) {
    if (!activeSessionId || isLoading) {
      return;
    }

    const localTurnId = createTurnId();
    setActiveView("chat");
    setIsLoading(true);
    setTurns((currentTurns) => [
      ...currentTurns,
      {
        id: localTurnId,
        question: originalQuestion,
        status: "loading",
      },
    ]);

    try {
      const result = await rerunSessionTurn(activeSessionId, turnId);
      setTurns((currentTurns) =>
        currentTurns.map((turn) =>
          turn.id === localTurnId
            ? {
                id: result.turn_id ?? turn.id,
                question: turn.question,
                status: "success",
                response: result,
                created_at: result.created_at,
              }
            : turn,
        ),
      );
      if (result.persisted) {
        void refreshSessions();
      }
    } catch (error) {
      const normalizedError = normalizeQueryError(error);
      setTurns((currentTurns) =>
        currentTurns.map((turn) =>
          turn.id === localTurnId
            ? {
                id: normalizedError.turn_id ?? turn.id,
                question: turn.question,
                status: "error",
                error: normalizedError,
                created_at: normalizedError.created_at,
              }
            : turn,
        ),
      );
      if (normalizedError.persisted) {
        void refreshSessions();
      }
    } finally {
      setIsLoading(false);
    }
  }

  async function handleExportTurn(turnId: string) {
    if (!activeSessionId) {
      return;
    }

    try {
      const blob = await exportSessionTurnCsv(activeSessionId, turnId);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `askdata-${turnId}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      // Keep the current view if export fails.
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
        promptGroups={examplePromptGroups}
        onNewChat={handleNewChat}
        onSelectPrompt={handleSelectPrompt}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onRenameSession={handleRenameSession}
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
                onExportTurn={handleExportTurn}
                onRerunTurn={handleRerunTurn}
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
      persisted: false,
    };
  }

  return {
    error: {
      code: "frontend_error",
      message: "An unexpected frontend error occurred.",
      details: {},
    },
    warnings: [],
    persisted: false,
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

function mapSessionDetailToTurns(session: SessionDetail): ConversationTurn[] {
  return session.turns.map((turn) => {
    if (turn.status === "success") {
      return {
        id: turn.id,
        question: turn.question,
        status: "success",
        response: turn.response,
        created_at: turn.created_at,
      };
    }

    return {
      id: turn.id,
      question: turn.question,
      status: "error",
      error: turn.error,
      created_at: turn.created_at,
    };
  });
}

function groupExamples(prompts: string[]): ExamplePromptGroup[] {
  const groups: ExamplePromptGroup[] = [
    { title: "Rankings", prompts: [] },
    { title: "Time trends", prompts: [] },
    { title: "Comparisons", prompts: [] },
    { title: "Follow-ups", prompts: [] },
  ];

  for (const prompt of prompts) {
    const normalizedPrompt = prompt.toLowerCase();
    if (normalizedPrompt.includes("top ") || normalizedPrompt.includes("most")) {
      groups[0].prompts.push(prompt);
      continue;
    }
    if (
      normalizedPrompt.includes("month") ||
      normalizedPrompt.includes("year") ||
      normalizedPrompt.includes("trend") ||
      normalizedPrompt.includes("quarter")
    ) {
      groups[1].prompts.push(prompt);
      continue;
    }
    if (
      normalizedPrompt.includes("compare") ||
      normalizedPrompt.includes("versus") ||
      normalizedPrompt.includes("vs")
    ) {
      groups[2].prompts.push(prompt);
      continue;
    }
    if (
      normalizedPrompt.includes("now ") ||
      normalizedPrompt.includes("only ") ||
      normalizedPrompt.includes("group ")
    ) {
      groups[3].prompts.push(prompt);
      continue;
    }

    groups[0].prompts.push(prompt);
  }

  return groups.filter((group) => group.prompts.length > 0);
}

