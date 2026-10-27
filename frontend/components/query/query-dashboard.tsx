"use client";

import { useEffect, useState } from "react";

import { ConnectDatabase } from "@/components/connect/connect-database";
import { Sidebar } from "@/components/layout/sidebar";
import type { DashboardView } from "@/components/layout/sidebar";
import { QuestionForm } from "@/components/query/question-form";
import { QueryWorkspace } from "@/components/query/query-workspace";
import { StartScreen } from "@/components/query/start-screen";
import { SchemaOverview } from "@/components/schema/schema-overview";
import {
  activateDemoDataSource,
  activateRuntimePostgresConnection,
  ApiError,
  disconnectRuntimeDataSource,
  exportSessionTurnCsv,
  fetchDataSources,
  fetchSchemaOverview,
  fetchSessionDetail,
  fetchSessions,
  queryAskData,
  renameSession,
  rerunSessionTurn,
  testRuntimePostgresConnection,
} from "@/lib/api";
import { getDatasetCopy, targetLabel } from "@/lib/datasets";
import { rowsToDelimited } from "@/lib/format";
import type {
  ConversationMessage,
  ConversationTurn,
  DataSourcesResponse,
  QueryErrorResponse,
  QueryResponse,
  RuntimeConnectionTestResponse,
  RuntimePostgresConnectionInput,
  SessionDetail,
  SessionSummary,
} from "@/lib/types";

type SuccessTurn = Extract<ConversationTurn, { status: "success" }>;

type QueryDashboardProps = {
  initialView?: DashboardView;
};

export function QueryDashboard({ initialView = "chat" }: QueryDashboardProps) {
  const [activeView, setActiveView] = useState<DashboardView>(initialView);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isChangingTarget, setIsChangingTarget] = useState(false);
  const [targetError, setTargetError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [dataSources, setDataSources] = useState<DataSourcesResponse | null>(null);
  const [tableCount, setTableCount] = useState<number | null>(null);
  const [schemaRefreshKey, setSchemaRefreshKey] = useState(0);

  const activeTarget = dataSources?.active_target ?? null;
  const persistenceAllowed = Boolean(activeTarget?.persistence_allowed);
  const customDbAllowed = dataSources?.custom_db_allowed ?? true;
  const copy = getDatasetCopy(activeTarget, tableCount);
  const busy = isLoading || isChangingTarget;

  useEffect(() => {
    let isActive = true;
    fetchDataSources()
      .then(async (sourceState) => {
        if (!isActive) {
          return;
        }
        setDataSources(sourceState);
        const sessionSummaries = sourceState.active_target.persistence_allowed
          ? await fetchSessions().catch(() => [] as SessionSummary[])
          : [];
        if (isActive) {
          setSessions(sessionSummaries);
        }
      })
      .catch(() => {
        if (isActive) {
          setTargetError("AskData can't reach its server. Start the backend and reload the page.");
        }
      });
    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    if (activeTarget?.target_type !== "runtime_postgres") {
      setTableCount(null);
      return;
    }
    let isActive = true;
    fetchSchemaOverview()
      .then((overview) => {
        if (isActive) {
          setTableCount(overview.tables.length);
        }
      })
      .catch(() => undefined);
    return () => {
      isActive = false;
    };
  }, [activeTarget?.target_type, activeTarget?.database_name, schemaRefreshKey]);

  async function runTurn(turnQuestion: string, request: () => Promise<QueryResponse>) {
    const localTurnId = createTurnId();
    const startedAt = performance.now();
    setActiveView("chat");
    setIsLoading(true);
    setTurns((current) => [...current, { id: localTurnId, question: turnQuestion, status: "loading" }]);

    try {
      const result = await request();
      const durationMs = performance.now() - startedAt;
      replaceTurn(localTurnId, {
        id: result.turn_id ?? localTurnId,
        question: turnQuestion,
        status: "success",
        response: result,
        created_at: result.created_at,
        duration_ms: durationMs,
      });
      if (result.session_id) {
        setActiveSessionId(result.session_id);
      }
      if (result.persisted) {
        void refreshSessions(true);
      }
    } catch (error) {
      const normalizedError = normalizeQueryError(error);
      replaceTurn(localTurnId, {
        id: normalizedError.turn_id ?? localTurnId,
        question: turnQuestion,
        status: "error",
        error: normalizedError,
        created_at: normalizedError.created_at,
      });
      if (normalizedError.session_id) {
        setActiveSessionId(normalizedError.session_id);
      }
      if (normalizedError.persisted) {
        void refreshSessions(true);
      }
    } finally {
      setIsLoading(false);
    }
  }

  function replaceTurn(localTurnId: string, nextTurn: ConversationTurn) {
    setTurns((current) => current.map((turn) => (turn.id === localTurnId ? nextTurn : turn)));
  }

  function ask(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) {
      return;
    }
    const conversationContext = buildConversationContext(turns);
    setQuestion("");
    void runTurn(trimmed, () =>
      queryAskData({
        question: trimmed,
        session_id: persistenceAllowed ? activeSessionId : null,
        conversation_context: conversationContext,
      }),
    );
  }

  function handleRunAgain(turnId: string, originalQuestion: string) {
    if (!activeSessionId || busy || !persistenceAllowed) {
      return;
    }
    const sessionId = activeSessionId;
    void runTurn(originalQuestion, () => rerunSessionTurn(sessionId, turnId));
  }

  async function handleDownloadCsv(turn: SuccessTurn) {
    let blob: Blob;
    if (persistenceAllowed && activeSessionId && turn.response.persisted) {
      try {
        blob = await exportSessionTurnCsv(activeSessionId, turn.id);
      } catch {
        blob = buildCsvBlob(turn.response);
      }
    } else {
      blob = buildCsvBlob(turn.response);
    }
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `askdata-${turn.id}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
  }

  async function refreshSessions(allowed: boolean) {
    if (!allowed) {
      setSessions([]);
      return;
    }
    try {
      setSessions(await fetchSessions());
    } catch {
      // Keep the last known list if the refresh fails.
    }
  }

  async function afterTargetChange() {
    const sourceState = await fetchDataSources();
    setDataSources(sourceState);
    setSchemaRefreshKey((current) => current + 1);
    resetChat();
    await refreshSessions(sourceState.active_target.persistence_allowed);
  }

  function resetChat() {
    setActiveSessionId(null);
    setQuestion("");
    setTurns([]);
  }

  async function changeTarget(action: () => Promise<unknown>) {
    setIsChangingTarget(true);
    setTargetError(null);
    try {
      await action();
      await afterTargetChange();
    } catch (error) {
      setTargetError(error instanceof Error ? error.message : "Switching the data failed.");
    } finally {
      setIsChangingTarget(false);
    }
  }

  function handleSelectTarget(targetId: string) {
    if (targetId === "demo_pagila" || targetId === "demo_retail_ops") {
      void changeTarget(() => activateDemoDataSource(targetId));
    }
  }

  function handleDisconnect() {
    void changeTarget(() => disconnectRuntimeDataSource());
  }

  async function handleTestConnection(payload: RuntimePostgresConnectionInput): Promise<RuntimeConnectionTestResponse> {
    return testRuntimePostgresConnection(payload);
  }

  async function handleConnect(payload: RuntimePostgresConnectionInput) {
    setIsChangingTarget(true);
    try {
      await activateRuntimePostgresConnection(payload);
      await afterTargetChange();
      setActiveView("chat");
    } finally {
      setIsChangingTarget(false);
    }
  }

  async function handleSelectSession(sessionId: string) {
    if (busy || !persistenceAllowed) {
      return;
    }
    try {
      const session = await fetchSessionDetail(sessionId);
      setActiveView("chat");
      setActiveSessionId(session.id);
      setQuestion("");
      setTurns(mapSessionDetailToTurns(session));
    } catch {
      // Keep the current conversation if the restore fails.
    }
  }

  async function handleRenameSession() {
    if (!activeSessionId || !persistenceAllowed) {
      return;
    }
    const current = sessions.find((session) => session.id === activeSessionId);
    const nextTitle = window.prompt("New name for this question", current?.title ?? "")?.trim();
    if (!nextTitle) {
      return;
    }
    try {
      const updated = await renameSession(activeSessionId, nextTitle);
      setSessions((list) =>
        list.map((session) => (session.id === updated.id ? { ...session, title: updated.title } : session)),
      );
    } catch {
      // Keep the old name if the rename fails.
    }
  }

  function handleNewQuestion() {
    if (busy) {
      return;
    }
    setActiveView("chat");
    resetChat();
  }

  const isEmptyChat = turns.length === 0;

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <Sidebar
        activeView={activeView}
        onSelectView={setActiveView}
        onNewQuestion={handleNewQuestion}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onRenameSession={handleRenameSession}
        busy={busy}
        activeTarget={activeTarget}
        demoTargets={dataSources?.demo_targets ?? []}
        runtimeTarget={dataSources?.runtime_target ?? null}
        customDbAllowed={customDbAllowed}
        onSelectTarget={handleSelectTarget}
        onDisconnectRuntimeTarget={handleDisconnect}
        targetError={targetError}
      />

      <main className="flex min-w-0 flex-1 flex-col md:h-screen">
        {activeView === "schema" ? (
          <div className="flex flex-1 justify-center overflow-y-auto px-4 py-10 md:px-6">
            <SchemaOverview
              key={schemaRefreshKey}
              targetName={activeTarget ? targetLabel(activeTarget) : "this database"}
            />
          </div>
        ) : null}

        {activeView === "connect" && customDbAllowed ? (
          <div className="flex flex-1 justify-center overflow-y-auto px-4 py-12 md:px-6">
            <ConnectDatabase onTest={handleTestConnection} onConnect={handleConnect} />
          </div>
        ) : null}

        {activeView === "chat" || (activeView === "connect" && !customDbAllowed) ? (
          <>
            <div
              className={`flex flex-1 justify-center overflow-y-auto px-4 md:px-6 ${
                isEmptyChat ? "items-center pb-6 pt-12" : "pb-6 pt-10"
              }`}
            >
              {isEmptyChat ? (
                <StartScreen copy={copy} disabled={busy} onAsk={ask} />
              ) : (
                <QueryWorkspace
                  turns={turns}
                  busy={busy}
                  allowRunAgain={persistenceAllowed && Boolean(activeSessionId)}
                  onAsk={ask}
                  onRunAgain={handleRunAgain}
                  onDownloadCsv={handleDownloadCsv}
                />
              )}
            </div>
            <div className="sticky bottom-0 flex justify-center bg-ground px-4 pb-6 pt-4 md:px-6">
              <QuestionForm
                question={question}
                isLoading={busy}
                placeholder={isEmptyChat ? copy.placeholder : copy.followUpPlaceholder}
                helper={isEmptyChat ? "AskData only reads your data. When a question is unclear, it asks first." : null}
                onQuestionChange={setQuestion}
                onSubmit={() => ask(question)}
              />
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
}

function buildCsvBlob(response: QueryResponse): Blob {
  return new Blob([rowsToDelimited(response.columns, response.rows, ",")], { type: "text/csv;charset=utf-8" });
}

function normalizeQueryError(error: unknown): QueryErrorResponse {
  if (error instanceof ApiError) {
    return error.payload;
  }
  return {
    error: {
      code: "frontend_error",
      message:
        error instanceof TypeError
          ? "AskData can't reach its server. Check that the backend is running and try again."
          : error instanceof Error
            ? error.message
            : "Something unexpected went wrong.",
      details: {},
    },
    warnings: [],
    persisted: false,
  };
}

function createTurnId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function buildConversationContext(turns: ConversationTurn[]): ConversationMessage[] {
  return turns
    .filter((turn): turn is SuccessTurn => turn.status === "success")
    .slice(-3)
    .flatMap((turn) => [
      { role: "user" as const, content: turn.question },
      { role: "assistant" as const, content: turn.response.answer_summary },
    ]);
}

function mapSessionDetailToTurns(session: SessionDetail): ConversationTurn[] {
  return session.turns.map((turn) =>
    turn.status === "success"
      ? { id: turn.id, question: turn.question, status: "success", response: turn.response, created_at: turn.created_at }
      : { id: turn.id, question: turn.question, status: "error", error: turn.error, created_at: turn.created_at },
  );
}
