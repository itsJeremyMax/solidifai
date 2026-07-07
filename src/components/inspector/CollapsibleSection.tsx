/**
 * CollapsibleSection — a labeled, collapsible block in the Inspector's Model tab.
 * Header: rotating chevron + uppercase title (+ optional mono count, + optional
 * right-aligned `action`). The body animates open/closed via a 0fr↔1fr grid row
 * (no max-height guessing). When closed the body is set `inert` so it leaves the
 * tab order and a11y tree while staying mounted for a smooth close animation.
 * The `action` sits beside the toggle button (a sibling, not nested inside it) so
 * an interactive action stays valid HTML and its click never toggles the section.
 */
import { useEffect, useRef } from "react";
import { ChevronDown } from "lucide-react";

export default function CollapsibleSection({
  title,
  count,
  open,
  onToggle,
  action,
  children,
}: {
  title: string;
  count?: number;
  open: boolean;
  onToggle: () => void;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const bodyId = `inspector-section-${title.replace(/\W+/g, "-").toLowerCase()}`;

  // `inert` removes the collapsed body from tab order + a11y tree without
  // unmounting it (so the open/close animation still plays both ways).
  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.inert = !open;
  }, [open]);

  return (
    <div className="border-b border-line">
      {/* Header row: the toggle fills the row so clicking the title/empty space
          collapses; the optional action is a sibling button, never nested. */}
      <div className="flex w-full items-center gap-2 px-3.5 pb-1.75 pt-2.75">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={bodyId}
          className="flex min-w-0 flex-1 items-center gap-2 text-micro font-bold uppercase tracking-eyebrow text-ink-3 transition-colors hover:text-ink-2"
        >
          <ChevronDown
            size={13}
            strokeWidth={2.4}
            className={`shrink-0 transition-transform duration-200 ${open ? "" : "-rotate-90"}`}
          />
          <span>{title}</span>
          {count !== undefined && (
            <span className="font-mono text-caption tracking-normal text-ink-3">{count}</span>
          )}
        </button>
        {action !== undefined && <span className="flex items-center">{action}</span>}
      </div>
      <div
        id={bodyId}
        className={`grid transition-[grid-template-rows] duration-200 ease-out-soft ${
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
        }`}
      >
        <div ref={bodyRef} className="overflow-hidden">
          {children}
        </div>
      </div>
    </div>
  );
}
