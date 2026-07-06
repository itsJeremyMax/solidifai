import { ChevronRight } from "lucide-react";

import { relativeTime, tildePath } from "../../lib/workspaces";
import { WorkspaceThumb } from "./WorkspaceThumb";
import { WorkspaceMenu } from "./WorkspaceMenu";
import Spinner from "../ui/Spinner";
import type { WorkspaceCardProps } from "./WorkspaceGridCard";
import { TagChips } from "./TagChips";

/**
 * Dense list-view row for a workspace. A small square thumbnail on the left
 * identifies the model at a glance; name + path are stacked in the middle;
 * on the right sit the edit time, optional part count, the ⋯ menu, and a
 * ChevronRight affordance.
 *
 * The identity area (thumbnail + name/path) is the open affordance button;
 * the WorkspaceMenu is a sibling so its buttons are never nested inside the
 * open button. Archived rows are dimmed and badged.
 */
export function WorkspaceListRow({
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
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  onAcceptName: _onAcceptName,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  onDismissName: _onDismissName,
  onTagClick,
}: WorkspaceCardProps) {
  const archived = ws.archivedAt != null;

  const timeLabel = archived
    ? `Archived ${relativeTime(ws.archivedAt)}`
    : `Edited ${relativeTime(ws.lastOpenedAt ?? ws.createdAt)}`;

  return (
    <div
      className={`group relative flex items-center gap-3.5 rounded-panel border border-line-2 bg-surface px-3 py-2.5 shadow-card transition-[transform,border-color,box-shadow] duration-200 ease-out-soft motion-safe:hover:-translate-y-px hover:border-accent-line hover:shadow-float ${
        archived ? "opacity-70" : ""
      } ${disabled ? "pointer-events-none opacity-55" : ""}`}
    >
      {/* Open affordance: thumbnail + name/path */}
      <button
        type="button"
        onClick={onOpen}
        disabled={disabled}
        className="flex min-w-0 flex-1 items-center gap-3.5 rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-line"
      >
        {/* Small square thumbnail — 54×54 */}
        <div className="relative h-[54px] w-[54px] shrink-0 overflow-hidden rounded-[9px] border border-line">
          <WorkspaceThumb name={ws.name} src={thumbSrc} className="h-full w-full" />
          {/* Archived overlay tint */}
          {archived && (
            <div
              className="absolute inset-0 bg-paper/40"
              aria-hidden
              style={{ filter: "saturate(0.55)" }}
            />
          )}
        </div>

        {/* Name + subtitle stack */}
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-sm font-bold tracking-snug text-ink">{ws.name}</span>
          {ws.description ? (
            <span className="truncate text-caption text-ink-2">{ws.description}</span>
          ) : (
            <span className="truncate font-mono text-micro text-ink-3">{tildePath(ws.path)}</span>
          )}
        </span>
      </button>

      {/* Tags — compact, between name area and time */}
      {ws.tags.length > 0 && (
        <span className="shrink-0">
          <TagChips tags={ws.tags} max={3} onTagClick={onTagClick} />
        </span>
      )}

      {/* Compact rename hint for list rows */}
      {!archived && ws.proposedName && (
        <span className="shrink-0 truncate text-caption text-amber-600">Rename suggested</span>
      )}

      {/* Right-side metadata */}
      <span className="w-30 shrink-0 text-right text-caption text-ink-3">{timeLabel}</span>

      {thumb != null && (
        <span className="w-16 shrink-0 text-right text-caption text-ink-3">
          {thumb.partCount} {thumb.partCount === 1 ? "part" : "parts"}
        </span>
      )}

      {/* Spinner — replaces chevron when busy */}
      {busy && (
        <span className="grid h-7 w-7 shrink-0 place-items-center">
          <Spinner size={15} className="text-ink-3" />
        </span>
      )}

      {/* ⋯ overflow menu */}
      <WorkspaceMenu
        archived={archived}
        onOpen={onOpen}
        onEditDetails={onEditDetails}
        onArchive={onArchive}
        onRestore={onRestore}
        onDelete={onDelete}
      />

      {/* Chevron open affordance hint */}
      {!busy && (
        <span className="grid h-7 w-4.5 shrink-0 place-items-center text-ink-3 transition-colors duration-150 group-hover:text-ink-2">
          <ChevronRight size={16} strokeWidth={1.7} />
        </span>
      )}
    </div>
  );
}
