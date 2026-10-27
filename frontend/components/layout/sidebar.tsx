"use client";

import { ChevronDownIcon, DatabaseIcon, PencilIcon, PlusIcon } from "@/components/ui/icons";
import { targetLabel } from "@/lib/datasets";
import type { DataSourceSummary, SessionSummary } from "@/lib/types";

export type DashboardView = "chat" | "schema" | "connect";

type SidebarProps = {
  activeView: DashboardView;
  onSelectView: (view: DashboardView) => void;
  onNewQuestion: () => void;
  sessions: SessionSummary[];
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onRenameSession: () => void;
  busy: boolean;
  activeTarget: DataSourceSummary | null;
  demoTargets: DataSourceSummary[];
  runtimeTarget: DataSourceSummary | null;
  customDbAllowed: boolean;
  onSelectTarget: (targetId: string) => void;
  onDisconnectRuntimeTarget: () => void;
  targetError: string | null;
};

const RUNTIME_TARGET_ID = "runtime_postgres";

export function Sidebar({
  activeView,
  onSelectView,
  onNewQuestion,
  sessions,
  activeSessionId,
  onSelectSession,
  onRenameSession,
  busy,
  activeTarget,
  demoTargets,
  runtimeTarget,
  customDbAllowed,
  onSelectTarget,
  onDisconnectRuntimeTarget,
  targetError,
}: SidebarProps) {
  const isRuntimeActive = activeTarget?.target_type === "runtime_postgres";
  const targetOptions = [
    ...demoTargets,
    ...(runtimeTarget ? [{ ...runtimeTarget, target_id: RUNTIME_TARGET_ID }] : []),
  ];
  const selectedTargetId = isRuntimeActive ? RUNTIME_TARGET_ID : (activeTarget?.target_id ?? "");

  return (
    <aside className="flex w-full flex-col gap-6 border-b border-line bg-sidebar px-5 py-6 md:sticky md:top-0 md:h-screen md:w-[248px] md:shrink-0 md:overflow-y-auto md:border-b-0 md:border-r">
      <button
        type="button"
        onClick={onNewQuestion}
        className="self-start text-xl font-semibold tracking-[-0.01em] text-ink"
      >
        AskData
      </button>

      <button
        type="button"
        onClick={onNewQuestion}
        disabled={busy}
        className="flex h-11 items-center gap-2 rounded-[10px] border border-inputLine bg-surface px-3.5 text-sm font-medium text-ink hover:border-muted disabled:cursor-not-allowed disabled:opacity-60"
      >
        <PlusIcon />
        New question
      </button>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="data-source" className="section-label">
          Data
        </label>
        <div className="relative">
          <DatabaseIcon className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink" />
          <select
            id="data-source"
            value={selectedTargetId}
            disabled={busy || targetOptions.length === 0}
            onChange={(event) => onSelectTarget(event.target.value)}
            className="h-11 w-full appearance-none rounded-[10px] border border-inputLine bg-surface pl-9 pr-9 text-sm font-medium text-ink disabled:cursor-not-allowed disabled:opacity-60"
          >
            {targetOptions.length === 0 ? <option value="">Loading…</option> : null}
            {targetOptions.map((target) => (
              <option key={target.target_id} value={target.target_id}>
                {targetLabel(target)}
              </option>
            ))}
          </select>
          <ChevronDownIcon className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-ink" />
        </div>
        {targetError ? <p className="text-[13px] leading-5 text-danger">{targetError}</p> : null}
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <button
            type="button"
            onClick={() => onSelectView(activeView === "schema" ? "chat" : "schema")}
            aria-pressed={activeView === "schema"}
            className="text-link min-h-8 text-left text-[13px]"
          >
            {activeView === "schema" ? "Back to questions" : "Browse tables"}
          </button>
          {isRuntimeActive ? (
            <button
              type="button"
              onClick={onDisconnectRuntimeTarget}
              disabled={busy}
              className="text-link min-h-8 text-left text-[13px]"
            >
              Disconnect
            </button>
          ) : null}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <div className="section-label mb-1">Recent</div>
        {isRuntimeActive ? (
          <p className="py-2 text-sm leading-5 text-muted">
            History is not saved for your own database.
          </p>
        ) : sessions.length === 0 ? (
          <p className="py-2 text-sm leading-5 text-muted">Your questions will appear here.</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {sessions.map((session) => {
              const selected = session.id === activeSessionId;
              return (
                <li key={session.id} className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => onSelectSession(session.id)}
                    disabled={busy}
                    aria-current={selected ? "true" : undefined}
                    className={`min-h-10 flex-1 rounded-lg px-2.5 py-2 text-left text-sm leading-5 disabled:cursor-not-allowed ${
                      selected ? "bg-line font-medium text-ink" : "text-inkSoft hover:bg-line/60"
                    }`}
                  >
                    {session.title}
                  </button>
                  {selected ? (
                    <button
                      type="button"
                      onClick={onRenameSession}
                      aria-label="Rename this question"
                      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-line/60 hover:text-ink"
                    >
                      <PencilIcon size={14} />
                    </button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {customDbAllowed ? (
        <button
          type="button"
          onClick={() => onSelectView("connect")}
          aria-pressed={activeView === "connect"}
          className="text-link flex min-h-11 items-center gap-2 text-left text-sm font-medium md:mt-auto"
        >
          <PlusIcon />
          Connect your database
        </button>
      ) : null}
    </aside>
  );
}
