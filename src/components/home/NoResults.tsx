import { Archive, Clock, SearchX } from "lucide-react";
import type { HomeFilter } from "../../lib/home";

interface NoResultsProps {
  query: string;
  filter: HomeFilter;
  onClear: () => void;
}

/**
 * Centered empty-state panel rendered when the filtered/searched workspace set
 * is empty but workspaces exist. Distinguishes between search-empty,
 * archived-empty, and recent-empty with distinct copy and icons.
 */
export function NoResults({ query, filter, onClear }: NoResultsProps) {
  const hasQuery = query.trim().length > 0;

  let icon: React.ReactNode;
  let title: string;
  let subtitle: string;
  let showClear = false;

  if (hasQuery) {
    icon = <SearchX size={26} strokeWidth={1.5} />;
    title = "No workspaces match";
    subtitle = `No results for "${query}"`;
    showClear = true;
  } else if (filter === "archived") {
    icon = <Archive size={26} strokeWidth={1.5} />;
    title = "Nothing archived";
    subtitle = "Workspaces you archive show up here.";
  } else {
    // filter === "recent"
    icon = <Clock size={26} strokeWidth={1.5} />;
    title = "Nothing recent";
    subtitle = "Workspaces you have opened lately show up here.";
  }

  return (
    <div className="flex flex-col items-center rounded-panel border border-dashed border-line-2 bg-surface/60 px-6 py-13 text-center">
      <span className="mb-4 grid h-13 w-13 place-items-center rounded-2xl border border-line-2 bg-surface text-ink-3 shadow-card motion-safe:animate-floaty">
        {icon}
      </span>
      <h3 className="mb-1 text-base font-semibold tracking-snug text-ink">{title}</h3>
      <p className="mb-0 max-w-72 text-body leading-normal text-ink-2">{subtitle}</p>
      {showClear && (
        <button
          type="button"
          onClick={onClear}
          className="mt-5 inline-flex h-8.5 items-center rounded-lg border border-line-2 bg-surface px-3.5 text-body font-medium text-ink-2 shadow-card transition-colors duration-150 hover:border-accent-line hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-line"
        >
          Clear search
        </button>
      )}
    </div>
  );
}
