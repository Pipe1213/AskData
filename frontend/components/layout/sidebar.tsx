import { ExamplePrompts } from "@/components/query/example-prompts";
import { UsedTablesPanel } from "@/components/result/used-tables-panel";

type SidebarView = "chat" | "schema";

type SidebarProps = {
  activeView: SidebarView;
  collapsed: boolean;
  onSelectView: (view: SidebarView) => void;
  onToggleCollapse: () => void;
  prompts: string[];
  onNewChat: () => void;
  onSelectPrompt: (prompt: string) => void;
  warnings: string[];
  usedTables: string[];
  isLoading: boolean;
};

export function Sidebar({
  activeView,
  collapsed,
  onSelectView,
  onToggleCollapse,
  prompts,
  onNewChat,
  onSelectPrompt,
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
          <ExamplePrompts
            prompts={prompts}
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
