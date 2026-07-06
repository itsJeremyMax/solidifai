import type { Workspace } from "../../lib/workspaces";
import { relativeTime, tildePath } from "../../lib/workspaces";
import type { ThumbMeta } from "../../lib/home";
import { WorkspaceThumb } from "./WorkspaceThumb";
import { WorkspaceMenu } from "./WorkspaceMenu";
import Spinner from "../ui/Spinner";
import { TagChips } from "./TagChips";

/**
 * Shared props interface for both WorkspaceGridCard and WorkspaceListRow.
 * Defined once here and re-exported so WorkspaceListRow can import it.
 */
export interface WorkspaceCardProps {
  ws: Workspace;
  thumbSrc: string | null;
  thumb?: ThumbMeta;
  busy: boolean;
  disabled: boolean;
  onOpen: () => void;
  onEditDetails: () => void;
  onArchive: () => void;
  onRestore: () => void;
  onDelete: () => void;
  onAcceptName: () => void;
  onDismissName: () => void;
  onTagClick?: (tag: string) => void;
}

/**
 * Grid-view workspace card. WorkspaceThumb fills the top ~150px; below it
 * sits the name, path, and a footer with edit time and optional part count.
 * The ⋯ WorkspaceMenu floats over the top-right corner.
 *
 * The whole body area (name / path / footer) is the open affordance button.
 * Archived cards are dimmed and carry a small badge on the render.
 */
export function WorkspaceGridCard({
  ws,
  thumbSrc,
  thumb,
  busy,
  disabled,
  onOpen,
  onEditDetails,
  onArchive,
  onRestore,
  onDelete,
  onAcceptName,
  onDismissName,
  onTagClick,
}: WorkspaceCardProps) {
  const archived = ws.archivedAt != null;

  const timeLabel = archived
    ? `Archived ${relativeTime(ws.archivedAt)}`
    : `Edited ${relativeTime(ws.lastOpenedAt ?? ws.createdAt)}`;

  return (
    <div
      className={`group relative overflow-hidden rounded-[13px] border border-line-2 bg-surface shadow-card transition-[transform,border-color,box-shadow] duration-200 ease-out-soft motion-safe:hover:-translate-y-0.5 hover:border-accent-line hover:shadow-float ${
        archived ? "opacity-70" : ""
      } ${disabled ? "pointer-events-none opacity-55" : ""}`}
    >
      {/* Render tile — full-width, ~150px tall */}
      <div className="relative h-[150px]">
        <WorkspaceThumb name={ws.name} src={thumbSrc} className="h-full w-full" />

        {/* Archived badge — top-left over render */}
        {archived && (
          <span className="absolute left-2 top-2 z-10 inline-flex items-center gap-1 rounded-full border border-line-2 bg-white/90 px-2 py-0.5 text-micro font-bold uppercase tracking-[0.04em] text-ink-2 backdrop-blur-sm">
            Archived
          </span>
        )}

        {/* Rename suggestion badge — only shown when active (not archived) */}
        {!archived && ws.proposedName && (
          <span className="absolute left-2 top-2 z-10 inline-flex items-center gap-1 rounded-full border border-amber-200/80 bg-amber-50/90 px-2 py-0.5 text-micro font-bold uppercase tracking-[0.04em] text-amber-700 backdrop-blur-sm">
            Rename suggested
          </span>
        )}

        {/* ⋯ menu — top-right over render */}
        <div className="absolute right-2 top-2 z-10">
          <WorkspaceMenu
            archived={archived}
            onOpen={onOpen}
            onEditDetails={onEditDetails}
            onArchive={onArchive}
            onRestore={onRestore}
            onDelete={onDelete}
          />
        </div>
      </div>

      {/* Card body — the open affordance */}
      <button
        type="button"
        onClick={onOpen}
        disabled={disabled}
        className={`w-full px-3.5 pt-2.75 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-line ${
          !archived && ws.proposedName ? "pb-2" : "rounded-b-[13px] pb-3.5"
        }`}
      >
        {/* Name + spinner */}
        <div className="flex items-center gap-2">
          <span className="flex-1 truncate text-sm font-bold leading-snug tracking-snug text-ink">
            {ws.name}
          </span>
          {busy && <Spinner size={13} className="shrink-0 text-ink-3" />}
        </div>

        {/* Description (2-line clamp) or path fallback when no description+tags */}
        {ws.description ? (
          <p className="mt-1 line-clamp-2 text-caption leading-relaxed text-ink-2">
            {ws.description}
          </p>
        ) : ws.tags.length === 0 ? (
          <p className="mt-0.75 truncate font-mono text-micro text-ink-3">{tildePath(ws.path)}</p>
        ) : null}

        {ws.tags.length > 0 && (
          <div className="mt-1.75">
            <TagChips tags={ws.tags} onTagClick={onTagClick} />
          </div>
        )}

        {/* Footer: edited time + optional part count */}
        <div className="mt-2.25 flex items-center gap-1.75 text-caption text-ink-3">
          <span>{timeLabel}</span>
          {thumb != null && (
            <>
              <span className="h-1 w-1 rounded-full bg-ink-3" aria-hidden />
              <span>
                {thumb.partCount} {thumb.partCount === 1 ? "part" : "parts"}
              </span>
            </>
          )}
        </div>
      </button>

      {/* Sol name suggestion — outside the open button to avoid nested interactive elements */}
      {!archived && ws.proposedName && (
        <div className="flex items-center gap-1.5 rounded-b-[13px] border-t border-line bg-surface-2/60 px-3.5 py-2 text-caption text-ink-2">
          <span>Sol suggests</span>
          <span className="flex-1 truncate font-semibold text-ink">{ws.proposedName}</span>
          <button
            type="button"
            onClick={onAcceptName}
            className="rounded px-1.5 py-0.5 text-micro font-semibold text-accent transition-colors duration-100 hover:bg-accent-tint focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent-line"
          >
            Accept
          </button>
          <button
            type="button"
            onClick={onDismissName}
            className="rounded px-1.5 py-0.5 text-micro font-semibold text-ink-3 transition-colors duration-100 hover:bg-surface-2 hover:text-ink-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-line-3"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
