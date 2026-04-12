"use client";

import { useState } from "react";

import { ExamplePrompts } from "@/components/query/example-prompts";
import type {
  DataSourceSummary,
  ExamplePromptGroup,
  RuntimeConnectionTestResponse,
  RuntimePostgresConnectionInput,
  SessionSummary,
  SslMode,
} from "@/lib/types";

type SidebarView = "chat" | "schema";

type SidebarProps = {
  activeView: SidebarView;
  collapsed: boolean;
  onSelectView: (view: SidebarView) => void;
  onToggleCollapse: () => void;
  promptGroups: ExamplePromptGroup[];
  onNewChat: () => void;
  onSelectPrompt: (prompt: string) => void;
  sessions: SessionSummary[];
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onRenameSession: () => void;
  isLoading: boolean;
  activeTarget: DataSourceSummary | null;
  demoTargets: DataSourceSummary[];
  runtimeTarget: DataSourceSummary | null;
  onActivateDemoTarget: (targetId: "demo_pagila" | "demo_retail_ops") => Promise<void>;
  onDisconnectRuntimeTarget: () => Promise<void>;
  onTestRuntimeConnection: (
    payload: RuntimePostgresConnectionInput,
  ) => Promise<RuntimeConnectionTestResponse>;
  onActivateRuntimeConnection: (payload: RuntimePostgresConnectionInput) => Promise<void>;
};

type RuntimeFormState = {
  host: string;
  port: string;
  database: string;
  user: string;
  password: string;
  sslmode: SslMode;
  schemaAllowlist: string;
};

const initialRuntimeForm: RuntimeFormState = {
  host: "",
  port: "5432",
  database: "",
  user: "",
  password: "",
  sslmode: "prefer",
  schemaAllowlist: "public",
};

export function Sidebar({
  activeView,
  collapsed,
  onSelectView,
  onToggleCollapse,
  promptGroups,
  onNewChat,
  onSelectPrompt,
  sessions,
  activeSessionId,
  onSelectSession,
  onRenameSession,
  isLoading,
  activeTarget,
  demoTargets,
  runtimeTarget,
  onActivateDemoTarget,
  onDisconnectRuntimeTarget,
  onTestRuntimeConnection,
  onActivateRuntimeConnection,
}: SidebarProps) {
  const [showRuntimeForm, setShowRuntimeForm] = useState(false);
  const [runtimeForm, setRuntimeForm] = useState<RuntimeFormState>(initialRuntimeForm);
  const [runtimeStatus, setRuntimeStatus] = useState<string | null>(null);
  const [runtimeWarnings, setRuntimeWarnings] = useState<string[]>([]);
  const [isTestingRuntime, setIsTestingRuntime] = useState(false);
  const [isActivatingRuntime, setIsActivatingRuntime] = useState(false);
  const [isChangingTarget, setIsChangingTarget] = useState(false);

  const isRuntimeActive = activeTarget?.target_type === "runtime_postgres";

  async function handleActivateDemoTarget(targetId: "demo_pagila" | "demo_retail_ops") {
    setIsChangingTarget(true);
    setRuntimeStatus(null);
    try {
      await onActivateDemoTarget(targetId);
      setShowRuntimeForm(false);
    } catch (error) {
      setRuntimeStatus(error instanceof Error ? error.message : "Failed to switch the demo target.");
    } finally {
      setIsChangingTarget(false);
    }
  }

  async function handleDisconnectRuntimeTarget() {
    setIsChangingTarget(true);
    setRuntimeStatus(null);
    try {
      await onDisconnectRuntimeTarget();
      setShowRuntimeForm(false);
      setRuntimeWarnings([]);
    } catch (error) {
      setRuntimeStatus(error instanceof Error ? error.message : "Failed to disconnect the runtime target.");
    } finally {
      setIsChangingTarget(false);
    }
  }

  async function handleTestRuntimeConnection() {
    setIsTestingRuntime(true);
    setRuntimeStatus(null);
    try {
      const result = await onTestRuntimeConnection(buildRuntimePayload(runtimeForm));
      setRuntimeWarnings(result.warnings);
      setRuntimeStatus(
        `Connected to PostgreSQL ${result.database_version}. ${result.table_count} tables visible across ${result.visible_schemas.length} schemas.`,
      );
    } catch (error) {
      setRuntimeWarnings([]);
      setRuntimeStatus(error instanceof Error ? error.message : "Connection test failed.");
    } finally {
      setIsTestingRuntime(false);
    }
  }

  async function handleActivateRuntimeConnection() {
    setIsActivatingRuntime(true);
    setRuntimeStatus(null);
    try {
      await onActivateRuntimeConnection(buildRuntimePayload(runtimeForm));
      setShowRuntimeForm(false);
      setRuntimeWarnings([]);
      setRuntimeStatus("Runtime PostgreSQL target activated.");
    } catch (error) {
      setRuntimeWarnings([]);
      setRuntimeStatus(error instanceof Error ? error.message : "Runtime activation failed.");
    } finally {
      setIsActivatingRuntime(false);
    }
  }

  return (
    <aside
      className={`panel h-full min-h-0 overflow-y-auto transition-all duration-200 ${
        collapsed ? "px-3 py-4 md:px-3 md:py-4" : "px-5 py-5 md:px-6 md:py-6"
      }`}
    >
      <section>
        <div className="flex items-start justify-between gap-3">
          <div>
            <button
              type="button"
              onClick={() => onSelectView("chat")}
              className="font-serif text-[2.2rem] leading-none tracking-[-0.05em] text-ink"
            >
              {collapsed ? "A" : "AskData"}
            </button>
            {!collapsed ? (
              <p className="mt-3 max-w-[28ch] text-sm leading-6 text-muted">
                Natural-language analytics over PostgreSQL with safe SQL execution and inspectable
                results.
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onToggleCollapse}
            className="inline-flex min-h-11 items-center rounded-full border border-line bg-white/75 px-3 py-2 text-sm font-medium text-ink transition hover:border-accent hover:text-accent"
          >
            {collapsed ? ">" : "<"}
          </button>
        </div>

        <button
          type="button"
          onClick={onNewChat}
          disabled={isLoading || isChangingTarget || isActivatingRuntime}
          className={`mt-4 inline-flex min-h-11 cursor-pointer items-center rounded-full border border-line bg-white/75 text-sm font-medium text-ink transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-60 ${
            collapsed ? "w-full justify-center px-2 py-2" : "px-4 py-2"
          }`}
        >
          {collapsed ? "New" : "New chat"}
        </button>
        <div className={`mt-4 flex ${collapsed ? "flex-col" : "flex-wrap"} gap-2`}>
          <button
            type="button"
            onClick={() => onSelectView("chat")}
            className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
              activeView === "chat"
                ? "border-accent bg-accentSoft text-accent"
                : "border-line bg-white/75 text-ink hover:border-accent hover:text-accent"
            } ${collapsed ? "w-full px-2" : ""}`}
          >
            Chat
          </button>
          <button
            type="button"
            onClick={() => onSelectView("schema")}
            className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
              activeView === "schema"
                ? "border-accent bg-accentSoft text-accent"
                : "border-line bg-white/75 text-ink hover:border-accent hover:text-accent"
            } ${collapsed ? "w-full px-2" : ""}`}
          >
            Schema
          </button>
        </div>
        {!collapsed ? (
          <div className="mt-5 text-sm font-medium text-ink">
            {isLoading ? "Assistant is preparing a response" : "Ready for the next question"}
          </div>
        ) : null}
      </section>

      {!collapsed ? (
        <section className="mt-6 border-t border-line pt-6">
          <div className="eyebrow">Data source</div>
          <h2 className="section-title mt-4">Active target</h2>
          <p className="mt-3 text-sm leading-6 text-muted">
            {activeTarget ? `${activeTarget.display_name} · ${formatTargetType(activeTarget)}` : "Loading target state..."}
          </p>
          {!isRuntimeActive ? (
            <p className="mt-2 text-sm leading-6 text-muted">
              Built-in demo switching reloads the local shared demo database in this phase.
            </p>
          ) : null}
          <div className="mt-4 space-y-2">
            {demoTargets.map((target) => (
              <button
                key={target.target_id}
                type="button"
                onClick={() =>
                  handleActivateDemoTarget(target.target_id as "demo_pagila" | "demo_retail_ops")
                }
                disabled={isLoading || isChangingTarget || isActivatingRuntime}
                className={`flex w-full items-center justify-between rounded-[18px] border px-4 py-3 text-left text-sm transition ${
                  target.is_active
                    ? "border-accent bg-accentSoft text-accent"
                    : "border-line bg-white/75 text-ink hover:border-accent hover:text-accent"
                } disabled:cursor-not-allowed disabled:opacity-60`}
              >
                <span>{target.display_name}</span>
                <span className="text-xs uppercase tracking-[0.16em]">
                  {target.is_active ? "Active" : "Demo"}
                </span>
              </button>
            ))}
            <button
              type="button"
              onClick={() => setShowRuntimeForm((current) => !current)}
              disabled={isLoading || isChangingTarget || isActivatingRuntime}
              className="flex w-full items-center justify-between rounded-[18px] border border-line bg-white/75 px-4 py-3 text-left text-sm text-ink transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span>Connect PostgreSQL</span>
              <span className="text-xs uppercase tracking-[0.16em]">
                {runtimeTarget ? "Configured" : "Runtime"}
              </span>
            </button>
            {isRuntimeActive ? (
              <button
                type="button"
                onClick={handleDisconnectRuntimeTarget}
                disabled={isLoading || isChangingTarget || isActivatingRuntime}
                className="w-full rounded-[18px] border border-line bg-white/75 px-4 py-3 text-left text-sm text-ink transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-60"
              >
                Disconnect runtime target
              </button>
            ) : null}
          </div>

          {showRuntimeForm ? (
            <div className="mt-5 space-y-3 rounded-[24px] border border-line bg-white/75 p-4">
              <RuntimeField
                label="Host"
                value={runtimeForm.host}
                onChange={(value) => setRuntimeForm((current) => ({ ...current, host: value }))}
                placeholder="localhost"
              />
              <div className="grid gap-3 sm:grid-cols-2">
                <RuntimeField
                  label="Port"
                  value={runtimeForm.port}
                  onChange={(value) => setRuntimeForm((current) => ({ ...current, port: value }))}
                  placeholder="5432"
                />
                <RuntimeField
                  label="SSL"
                  value={runtimeForm.sslmode}
                  onChange={(value) =>
                    setRuntimeForm((current) => ({ ...current, sslmode: value as SslMode }))
                  }
                  as="select"
                  options={[
                    { label: "Prefer", value: "prefer" },
                    { label: "Require", value: "require" },
                    { label: "Disable", value: "disable" },
                  ]}
                />
              </div>
              <RuntimeField
                label="Database"
                value={runtimeForm.database}
                onChange={(value) =>
                  setRuntimeForm((current) => ({ ...current, database: value }))
                }
                placeholder="analytics"
              />
              <RuntimeField
                label="User"
                value={runtimeForm.user}
                onChange={(value) => setRuntimeForm((current) => ({ ...current, user: value }))}
                placeholder="postgres"
              />
              <RuntimeField
                label="Password"
                value={runtimeForm.password}
                onChange={(value) =>
                  setRuntimeForm((current) => ({ ...current, password: value }))
                }
                placeholder="Required for this phase"
                type="password"
              />
              <RuntimeField
                label="Schemas"
                value={runtimeForm.schemaAllowlist}
                onChange={(value) =>
                  setRuntimeForm((current) => ({ ...current, schemaAllowlist: value }))
                }
                placeholder="public, analytics"
              />
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  onClick={handleTestRuntimeConnection}
                  disabled={isTestingRuntime || isActivatingRuntime}
                  className="rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-ink transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isTestingRuntime ? "Testing..." : "Test connection"}
                </button>
                <button
                  type="button"
                  onClick={handleActivateRuntimeConnection}
                  disabled={isTestingRuntime || isActivatingRuntime}
                  className="rounded-full border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isActivatingRuntime ? "Connecting..." : "Connect and use"}
                </button>
              </div>
              {runtimeStatus ? (
                <p className="text-sm leading-6 text-muted">{runtimeStatus}</p>
              ) : null}
              {runtimeWarnings.length > 0 ? (
                <div className="space-y-2">
                  {runtimeWarnings.map((warning, index) => (
                    <p key={`${warning}-${index}`} className="text-sm leading-6 text-muted">
                      {warning}
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {isRuntimeActive ? (
            <p className="mt-4 text-sm leading-6 text-muted">
              Runtime PostgreSQL connection active. Persistent history is disabled in this mode for now.
            </p>
          ) : null}
        </section>
      ) : null}

      {!collapsed ? (
        <section className="mt-6 border-t border-line pt-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="eyebrow">History</div>
              <h2 className="section-title mt-4">Recent sessions</h2>
            </div>
            {activeSessionId && !isRuntimeActive ? (
              <button
                type="button"
                onClick={onRenameSession}
                className="text-sm font-medium text-accent transition hover:opacity-80"
              >
                Rename
              </button>
            ) : null}
          </div>
          {isRuntimeActive ? (
            <p className="mt-4 text-sm leading-6 text-muted">
              Runtime PostgreSQL connection active. Persistent history, reopen, and rename are disabled.
            </p>
          ) : (
            <div className="mt-4 space-y-2">
              {sessions.length > 0 ? (
                sessions.map((session) => (
                  <button
                    key={session.id}
                    type="button"
                    onClick={() => onSelectSession(session.id)}
                    className={`flex w-full flex-col items-start rounded-[20px] px-3 py-3 text-left transition ${
                      session.id === activeSessionId
                        ? "bg-accentSoft text-accent"
                        : "hover:bg-white/70"
                    }`}
                  >
                    <span className="text-sm font-semibold leading-6">{session.title}</span>
                    <span className="text-xs leading-5 text-muted">
                      {session.turn_count} turns
                      {session.last_status ? ` · ${session.last_status}` : ""}
                    </span>
                  </button>
                ))
              ) : (
                <p className="text-sm leading-6 text-muted">
                  Session history appears here after the first persisted question.
                </p>
              )}
            </div>
          )}
        </section>
      ) : null}

      {!collapsed && !isRuntimeActive ? (
        <section className="mt-6 border-t border-line pt-6">
          <ExamplePrompts
            groups={promptGroups}
            disabled={isLoading}
            onSelectPrompt={onSelectPrompt}
            variant="compact"
          />
        </section>
      ) : null}
    </aside>
  );
}

type RuntimeFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  as?: "input" | "select";
  options?: Array<{ label: string; value: string }>;
};

function RuntimeField({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  as = "input",
  options = [],
}: RuntimeFieldProps) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.16em] text-muted">
        {label}
      </span>
      {as === "select" ? (
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="w-full rounded-[18px] border border-line bg-white px-4 py-3 text-sm leading-6 text-ink outline-none transition focus:border-accent"
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="w-full rounded-[18px] border border-line bg-white px-4 py-3 text-sm leading-6 text-ink outline-none transition focus:border-accent"
        />
      )}
    </label>
  );
}

function buildRuntimePayload(form: RuntimeFormState): RuntimePostgresConnectionInput {
  return {
    host: form.host.trim(),
    port: Number(form.port) || 5432,
    database: form.database.trim(),
    user: form.user.trim(),
    password: form.password,
    sslmode: form.sslmode,
    schema_allowlist: form.schemaAllowlist
      .split(",")
      .map((schema) => schema.trim())
      .filter(Boolean),
  };
}

function formatTargetType(target: DataSourceSummary): string {
  if (target.target_type === "runtime_postgres") {
    return "runtime PostgreSQL";
  }
  return "demo dataset";
}
