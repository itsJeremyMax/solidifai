import type { Ref } from "react";
import { LayoutGrid, List, Plus, Search, X } from "lucide-react";
import type { HomeFilter, ViewMode } from "../../lib/home";
import { ACCENT_CTA } from "../../lib/styles";

interface LibraryToolbarProps {
  query: string;
  onQuery: (q: string) => void;
  filter: HomeFilter;
  onFilter: (f: HomeFilter) => void;
  view: ViewMode;
  onView: (v: ViewMode) => void;
  onNew: () => void;
  counts: { all: number; archived: number };
  /** Optional ref to the search input so a ⌘K shortcut can focus it. */
  inputRef?: Ref<HTMLInputElement>;
  tagFilter: string | null;
  onClearTag: () => void;
}

export function LibraryToolbar({
  query,
  onQuery,
  filter,
  onFilter,
  view,
  onView,
  onNew,
  counts,
  inputRef,
  tagFilter,
  onClearTag,
}: LibraryToolbarProps) {
  return (
    <div className="flex items-center gap-2.5">
      {/* Search box */}
      <div className="flex h-11 w-96 shrink-0 items-center gap-2.5 rounded-[11px] border border-line-2 bg-surface px-3.5 shadow-[0_1px_2px_rgba(16,18,24,.04)] focus-within:border-accent-line focus-within:ring-2 focus-within:ring-accent-tint">
        <Search size={15} strokeWidth={2} className="shrink-0 text-ink-3" aria-hidden />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="Search workspaces"
          aria-label="Search workspaces"
          autoComplete="off"
          spellCheck={false}
          className="min-w-0 flex-1 bg-transparent text-body text-ink placeholder:text-ink-3 focus:outline-none"
        />
        <kbd className="shrink-0 rounded-[5px] border border-line-2 bg-surface-2 px-1.5 py-px font-mono text-caption text-ink-3">
          ⌘K
        </kbd>
      </div>

      {/* Segmented filter */}
      <div
        role="group"
        aria-label="Filter workspaces"
        className="inline-flex h-11 items-center gap-0.5 rounded-[11px] border border-line-2 bg-surface-2 p-[3px]"
      >
        {(
          [
            { key: "all" as const, label: "All", count: counts.all },
            { key: "recent" as const, label: "Recent", count: null },
            { key: "archived" as const, label: "Archived", count: counts.archived },
          ] satisfies { key: HomeFilter; label: string; count: number | null }[]
        ).map(({ key, label, count }) => {
          const active = filter === key;
          return (
            <button
              key={key}
              type="button"
              aria-pressed={active}
              onClick={() => onFilter(key)}
              className={[
                "inline-flex h-9.5 items-center gap-1.5 rounded-lg px-3.5 text-caption font-semibold transition-colors duration-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-line",
                active
                  ? "bg-surface text-ink shadow-[0_1px_2px_rgba(16,18,24,.08)]"
                  : "text-ink-2 hover:text-ink",
              ].join(" ")}
            >
              {label}
              {count !== null && (
                <span
                  className={["text-micro font-bold", active ? "text-accent" : "text-ink-3"].join(
                    " ",
                  )}
                  aria-hidden
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Active tag filter pill */}
      {tagFilter && (
        <span className="inline-flex items-center gap-1 rounded-full border border-line-2 bg-surface-2 px-2.5 py-1 text-micro font-semibold text-ink-2">
          #{tagFilter}
          <button
            type="button"
            aria-label="Clear tag filter"
            onClick={onClearTag}
            className="ml-0.5 grid h-4 w-4 place-items-center rounded-full text-ink-3 transition-colors duration-100 hover:bg-surface-3 hover:text-ink-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent-line"
          >
            <X size={10} strokeWidth={2.5} aria-hidden />
          </button>
        </span>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* View toggle */}
      <div
        role="group"
        aria-label="View mode"
        className="inline-flex h-11 overflow-hidden rounded-[11px] border border-line-2 bg-surface"
      >
        <button
          type="button"
          aria-label="Grid view"
          aria-pressed={view === "grid"}
          onClick={() => onView("grid")}
          className={[
            "flex w-11 items-center justify-center transition-colors duration-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-line",
            view === "grid" ? "bg-accent-tint" : "hover:bg-surface-2",
          ].join(" ")}
        >
          <LayoutGrid
            size={15}
            strokeWidth={1.75}
            className={view === "grid" ? "text-accent" : "text-ink-3"}
            aria-hidden
          />
        </button>
        <button
          type="button"
          aria-label="List view"
          aria-pressed={view === "list"}
          onClick={() => onView("list")}
          className={[
            "flex w-11 items-center justify-center border-l border-line-2 transition-colors duration-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-line",
            view === "list" ? "bg-accent-tint" : "hover:bg-surface-2",
          ].join(" ")}
        >
          <List
            size={15}
            strokeWidth={1.75}
            className={view === "list" ? "text-accent" : "text-ink-3"}
            aria-hidden
          />
        </button>
      </div>

      {/* New workspace CTA */}
      <button
        type="button"
        onClick={onNew}
        className={`${ACCENT_CTA} h-11 px-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-line focus-visible:ring-offset-1`}
      >
        <Plus size={15} strokeWidth={2.5} aria-hidden />
        New workspace
      </button>
    </div>
  );
}
