import { ExamplePrompts } from "@/components/query/example-prompts";
import { UsedTablesPanel } from "@/components/result/used-tables-panel";
import type { ExamplePromptGroup, SessionSummary } from "@/lib/types";

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
  warnings: string[];
  usedTables: string[];
  isLoading: boolean;
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
  warnings,
  usedTables,
  isLoading,
}: SidebarProps) {
  const displayedWarnings =
    warnings.length > 0
      ? warnings
      : [
          isLoading
            ? "The backend is currently processing the question."
            : "Warnings appear here only when the backend has something important to surface.",
        ];

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
          disabled={isLoading}
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
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="eyebrow">History</div>
              <h2 className="section-title mt-4">Recent sessions</h2>
            </div>
            {activeSessionId ? (
              <button
                type="button"
                onClick={onRenameSession}
                className="text-sm font-medium text-accent transition hover:opacity-80"
              >
                Rename
              </button>
            ) : null}
          </div>
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
        </section>
      ) : null}

      {!collapsed ? (
        <section className="mt-6 border-t border-line pt-6">
          <ExamplePrompts
            groups={promptGroups}
            disabled={isLoading}
            onSelectPrompt={onSelectPrompt}
            variant="compact"
          />
        </section>
      ) : null}

      {!collapsed ? (
        <section className="mt-6 border-t border-line pt-6">
          <div className="eyebrow">Warnings</div>
          <h2 className="section-title mt-4">Things to notice</h2>
          <p className="section-copy mt-3">
            If the backend repaired a query, used a proxy, or found ambiguity, it appears here.
          </p>
          <div className="mt-5 space-y-3">
            {displayedWarnings.map((warning, index) => (
              <div
                key={`${warning}-${index}`}
                className="border-l-2 border-line pl-4 text-sm leading-6 text-muted"
              >
                {warning}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {!collapsed ? (
        <section className="mt-6 border-t border-line pt-6">
          <UsedTablesPanel
            title="Latest used tables"
            description="These are the real tables reported by the backend after validation and execution."
            tables={usedTables}
            variant="compact"
          />
        </section>
      ) : null}
    </aside>
  );
}
