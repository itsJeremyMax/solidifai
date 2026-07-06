/**
 * History — the Inspector's "History" section body. Owns its own live history
 * state (it doesn't piggyback on AppShell's `useArtifacts`), so it needs no new
 * props threaded down:
 *
 *   mount                 → engine_history → set entries
 *   "model-updated"       → re-fetch engine_history (every engine rebuild,
 *                           including undo/redo/goto, flows through here so the
 *                           list + the highlighted "current" row stay live).
 *
 * Rows are rendered newest-first. The `current` entry gets the Inspector's
 * accent-tint selected-row treatment (matching the Model Tree's first row) plus
 * a filled accent dot; the others show a hollow dot and navigate on click via
 * `engine_goto(index)`. The rebuild echoes back through `model-updated`, which
 * re-fetches and moves the highlight — so a goto is fire-and-forget here.
 *
 * Mirrors the listener lifecycle in `useArtifacts` (cancelled flag + unlisten on
 * unmount) so a missing/late backend leaves a clean empty state, never a throw.
 */
import { useEffect, useState } from "react";

import { engineGoto, engineHistory, onModelUpdated, type HistoryEntry } from "../lib/ipc";
import { relativeTime } from "../lib/workspaces";

export default function History() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      const state = await engineHistory();
      if (cancelled) return;
      setEntries(state?.entries ?? []);
    };

    void refresh();

    let unlisten: (() => void) | undefined;
    onModelUpdated(() => {
      void refresh();
    })
      .then((fn) => {
        if (cancelled) fn();
        else unlisten = fn;
      })
      .catch(() => {
        // Backend not available — initial empty state stands.
      });

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  if (entries.length === 0) {
    return <div className="px-3.5 pb-2.5 pt-0.5 text-xs text-ink-3">No history yet</div>;
  }

  // Newest-first: the engine returns entries oldest→newest by index; render the
  // reverse so the most recent edit sits at the top of the section.
  const ordered = [...entries].reverse();

  return (
    <div className="pb-1.5">
      <div className="flex items-center justify-between px-3.5 pb-1.75 pt-2.75 text-micro font-bold uppercase tracking-eyebrow text-ink-3">
        <span>History</span>
        <span className="font-mono text-caption tracking-normal">
          {entries.length} {entries.length === 1 ? "state" : "states"}
        </span>
      </div>
      {ordered.map((entry) => (
        <Row key={entry.sha} entry={entry} />
      ))}
    </div>
  );
}

/** A single history row. Current = accent-tint + filled dot, non-interactive. */
function Row({ entry }: { entry: HistoryEntry }) {
  const isCurrent = entry.current;

  return (
    <div
      // Only navigable rows are buttons; the current row is a plain, inert
      // marker (a `role="button"` here would have screen readers announce a
      // button that does nothing). `aria-current` still flags it as active.
      role={isCurrent ? undefined : "button"}
      tabIndex={isCurrent ? undefined : 0}
      aria-current={isCurrent || undefined}
      onClick={() => {
        if (!isCurrent) void engineGoto(entry.index);
      }}
      onKeyDown={
        isCurrent
          ? undefined
          : (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                void engineGoto(entry.index);
              }
            }
      }
      title={isCurrent ? "Current state" : `Restore: ${entry.message}`}
      className={
        isCurrent
          ? "flex cursor-default items-center gap-2.25 bg-accent-tint px-3.5 py-1.75 text-body"
          : "flex cursor-pointer items-center gap-2.25 px-3.5 py-1.75 text-body transition-colors duration-100 hover:bg-surface-2"
      }
    >
      <span
        className={
          isCurrent
            ? "h-1.75 w-1.75 shrink-0 rounded-full bg-accent"
            : "h-1.75 w-1.75 shrink-0 rounded-full border border-ink-3/40"
        }
      />

      {/* commit message — takes remaining space, truncated. `min-w-0` lets the
          flex item shrink below its content width so `truncate` engages (the
          two trailing mono labels are `shrink-0` and must never be squeezed). */}
      <span className={`min-w-0 flex-1 truncate ${isCurrent ? "text-ink" : "text-ink-2"}`}>
        {entry.message}
      </span>

      <span className="shrink-0 font-mono text-caption text-ink-3/60">{entry.sha.slice(0, 6)}</span>

      {/* relative time — epoch seconds → millis for the shared formatter */}
      <span className="shrink-0 font-mono text-caption text-ink-3">
        {relativeTime(entry.time * 1000)}
      </span>
    </div>
  );
}
