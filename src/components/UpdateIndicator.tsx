/**
 * UpdateIndicator — the always-available top-bar anchor for an update. Renders a
 * quiet pill in the header (nothing while idle/checking) and, on click, opens a
 * popover with the full {@link UpdateCard}: version, release notes, progress, and
 * actions. This is the persistent entry point; the {@link UpdateCompanion} card
 * is the same content surfaced proactively on launch.
 *
 * The pill's label tracks the lifecycle (available → downloading → restart →
 * failed); opening the popover never itself starts a download — the user acts
 * from inside the card.
 */
import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, RotateCw, TriangleAlert } from "lucide-react";

import { useUpdater } from "../state/updater";
import { useOnUpdatesPage } from "../hooks/useOnUpdatesPage";
import UpdateCard from "./update/UpdateCard";
import Reveal from "./update/Reveal";

const ICON_STROKE = 1.8;

export default function UpdateIndicator() {
  const { status, version, progress, dismiss } = useUpdater();
  const onUpdatesPage = useOnUpdatesPage();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Opening the anchor's popover folds the companion toast, so the same card is
  // never shown twice at once.
  const toggleOpen = () =>
    setOpen((v) => {
      if (!v) dismiss();
      return !v;
    });

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // No anchor while idle or during a silent/manual check; and none on the Updates
  // settings page, where the page itself is the single update surface.
  const hidden = status === "idle" || status === "checking" || onUpdatesPage;

  // Collapse the popover when the anchor hides, so it doesn't auto-expand if the
  // indicator later reappears for a new update.
  useEffect(() => {
    if (hidden && open) setOpen(false);
  }, [hidden, open]);

  if (hidden) return null;

  const pct = progress === null ? null : Math.round(progress * 100);

  const pill = (() => {
    if (status === "downloading") {
      return (
        <button
          type="button"
          onClick={toggleOpen}
          title="Update downloading"
          className="inline-flex h-8 shrink-0 select-none items-center gap-2.25 whitespace-nowrap rounded-lg border border-line-2 bg-surface px-2.75 text-body font-medium text-ink-2 transition-colors duration-150 hover:border-line-3"
        >
          <span>{pct === null ? "Downloading…" : `Downloading ${pct}%`}</span>
          <span className="relative h-1 w-16 overflow-hidden rounded-full bg-line-2">
            <span
              className="absolute inset-y-0 left-0 rounded-full bg-accent transition-[width] duration-200"
              style={{ width: `${progress === null ? 100 : Math.max(4, (progress ?? 0) * 100)}%` }}
            />
          </span>
        </button>
      );
    }
    if (status === "ready") {
      return (
        <button
          type="button"
          onClick={toggleOpen}
          title="Update ready, restart to finish"
          className="inline-flex h-8 shrink-0 items-center gap-1.75 whitespace-nowrap rounded-lg border border-accent-line bg-accent-tint px-2.75 text-body font-medium text-accent transition-colors duration-150 hover:border-accent"
        >
          <RotateCw size={15} strokeWidth={ICON_STROKE} />
          Restart to update
        </button>
      );
    }
    if (status === "error") {
      return (
        <button
          type="button"
          onClick={toggleOpen}
          title="The update did not finish"
          className="inline-flex h-8 shrink-0 items-center gap-1.75 whitespace-nowrap rounded-lg border border-danger-line bg-surface px-2.75 text-body font-medium text-danger transition-colors duration-150 hover:bg-danger-bg"
        >
          <TriangleAlert size={15} strokeWidth={ICON_STROKE} />
          Update failed
        </button>
      );
    }
    // available
    return (
      <button
        type="button"
        onClick={toggleOpen}
        title="Update available"
        className="inline-flex h-8 shrink-0 items-center gap-1.75 whitespace-nowrap rounded-lg border border-accent-line bg-accent-tint px-2.75 text-body font-medium text-accent transition-colors duration-150 hover:border-accent"
      >
        <ArrowDownToLine size={15} strokeWidth={ICON_STROKE} />
        {version ? `Update available v${version}` : "Update available"}
      </button>
    );
  })();

  return (
    <div ref={wrapRef} className="relative">
      {pill}
      {open && (
        <Reveal className="absolute right-0 top-full z-50 mt-2">
          <UpdateCard onClose={() => setOpen(false)} />
        </Reveal>
      )}
    </div>
  );
}
