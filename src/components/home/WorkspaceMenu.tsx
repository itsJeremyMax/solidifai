import { useCallback, useState } from "react";
import { Archive, ArrowUpRight, MoreVertical, Pencil, RotateCcw, Trash2 } from "lucide-react";

import { useDismiss } from "../../hooks/useDismiss";
import { MENU_PANEL } from "../../lib/styles";

/** Lucide stroke weight consistent with the Launcher card's icon language. */
const ICON_STROKE = 1.7;

export interface WorkspaceMenuProps {
  archived: boolean;
  onOpen: () => void;
  onEditDetails: () => void;
  onArchive: () => void;
  onRestore: () => void;
  onDelete: () => void;
}

/**
 * The ⋯ overflow button + dropdown for a workspace card or list row.
 * Manages its own open/closed state; closes on outside-click or Escape
 * via useDismiss. Wired icon + label for each action.
 */
export function WorkspaceMenu({
  archived,
  onOpen,
  onEditDetails,
  onArchive,
  onRestore,
  onDelete,
}: WorkspaceMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useDismiss<HTMLDivElement>(
    open,
    useCallback(() => setOpen(false), []),
  );

  function act(handler: () => void) {
    setOpen(false);
    handler();
  }

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Workspace actions"
        className={`grid h-7 w-7 place-items-center rounded-lg border backdrop-blur-sm transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-line ${
          open
            ? "border-accent-line bg-white/90 text-ink shadow-sm"
            : "border-line-2 bg-white/85 text-ink-2 hover:border-accent-line hover:bg-white/90 hover:text-ink"
        }`}
      >
        <MoreVertical size={14} strokeWidth={ICON_STROKE} />
      </button>

      {open && (
        <div className={`${MENU_PANEL} right-0 top-8.5 w-44`}>
          {!archived ? (
            <>
              {/* Open */}
              <button
                type="button"
                onClick={() => act(onOpen)}
                className="flex w-full items-center gap-2.25 rounded-lg px-2.5 py-2 text-left text-body text-ink transition-colors duration-150 hover:bg-surface-2 focus-visible:outline-none focus-visible:bg-surface-2"
              >
                <ArrowUpRight className="text-ink-3" size={15} strokeWidth={ICON_STROKE} />
                Open
              </button>

              {/* Edit details */}
              <button
                type="button"
                onClick={() => act(onEditDetails)}
                className="flex w-full items-center gap-2.25 rounded-lg px-2.5 py-2 text-left text-body text-ink transition-colors duration-150 hover:bg-surface-2 focus-visible:outline-none focus-visible:bg-surface-2"
              >
                <Pencil className="text-ink-3" size={15} strokeWidth={ICON_STROKE} />
                Edit details
              </button>

              {/* Archive */}
              <button
                type="button"
                onClick={() => act(onArchive)}
                className="flex w-full items-center gap-2.25 rounded-lg px-2.5 py-2 text-left text-body text-ink transition-colors duration-150 hover:bg-surface-2 focus-visible:outline-none focus-visible:bg-surface-2"
              >
                <Archive className="text-ink-3" size={15} strokeWidth={ICON_STROKE} />
                Archive
              </button>

              {/* divider */}
              <div className="my-1.25 mx-1.5 h-px bg-line" aria-hidden />

              {/* Delete */}
              <button
                type="button"
                onClick={() => act(onDelete)}
                className="flex w-full items-center gap-2.25 rounded-lg px-2.5 py-2 text-left text-body text-danger transition-colors duration-150 hover:bg-danger-bg focus-visible:outline-none focus-visible:bg-danger-bg"
              >
                <Trash2 size={15} strokeWidth={ICON_STROKE} />
                Delete
              </button>
            </>
          ) : (
            <>
              {/* Restore */}
              <button
                type="button"
                onClick={() => act(onRestore)}
                className="flex w-full items-center gap-2.25 rounded-lg px-2.5 py-2 text-left text-body text-ink transition-colors duration-150 hover:bg-surface-2 focus-visible:outline-none focus-visible:bg-surface-2"
              >
                <RotateCcw className="text-ink-3" size={15} strokeWidth={ICON_STROKE} />
                Restore
              </button>

              {/* divider */}
              <div className="my-1.25 mx-1.5 h-px bg-line" aria-hidden />

              {/* Delete */}
              <button
                type="button"
                onClick={() => act(onDelete)}
                className="flex w-full items-center gap-2.25 rounded-lg px-2.5 py-2 text-left text-body text-danger transition-colors duration-150 hover:bg-danger-bg focus-visible:outline-none focus-visible:bg-danger-bg"
              >
                <Trash2 size={15} strokeWidth={ICON_STROKE} />
                Delete
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
