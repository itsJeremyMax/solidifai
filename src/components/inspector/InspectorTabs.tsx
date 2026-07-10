/**
 * InspectorTabs — the Inspector header's segmented control. Equal-width cells
 * with always-visible labels and a sliding indicator, so the row's geometry
 * never changes when the active tab does. Arrow keys move the selection.
 */
import { useRef } from "react";

import { INSPECTOR_TABS, type InspectorTab } from "./tabs";

export type { InspectorTab };

export default function InspectorTabs({
  active,
  onSelect,
  badges,
}: {
  active: InspectorTab;
  onSelect: (t: InspectorTab) => void;
  /** Tabs that should show a corner dot (quiet "something new here" signal). */
  badges?: Partial<Record<InspectorTab, boolean>>;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const activeIdx = Math.max(
    0,
    INSPECTOR_TABS.findIndex((t) => t.id === active),
  );

  const selectIdx = (idx: number) => {
    const n = INSPECTOR_TABS.length;
    const next = INSPECTOR_TABS[((idx % n) + n) % n];
    onSelect(next.id);
    // Selection follows focus: keep the keyboard on the newly active tab.
    listRef.current?.querySelector<HTMLButtonElement>(`[data-tab="${next.id}"]`)?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight") selectIdx(activeIdx + 1);
    else if (e.key === "ArrowLeft") selectIdx(activeIdx - 1);
    else if (e.key === "Home") selectIdx(0);
    else if (e.key === "End") selectIdx(INSPECTOR_TABS.length - 1);
    else return;
    e.preventDefault();
  };

  return (
    <div
      ref={listRef}
      role="tablist"
      aria-label="Inspector sections"
      onKeyDown={handleKeyDown}
      className="relative flex h-7.5 min-w-0 flex-1 rounded-lg bg-surface-2 p-0.75"
    >
      {/* Sliding indicator: one card, translated to the active cell. */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-y-0.75 left-0.75 rounded-md bg-surface shadow-[0_1px_2px_rgba(16,18,24,0.07),0_0_0_1px_var(--color-line)] transition-transform duration-200 ease-out-soft motion-reduce:transition-none"
        style={{
          width: `calc((100% - 6px) / ${INSPECTOR_TABS.length})`,
          transform: `translateX(${activeIdx * 100}%)`,
        }}
      />
      {INSPECTOR_TABS.map(({ id, label }) => {
        const on = active === id;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            data-tab={id}
            aria-selected={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onSelect(id)}
            className={`relative z-[1] min-w-0 flex-1 rounded-md text-caption transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-line ${
              on ? "font-semibold text-ink" : "font-medium text-ink-3 hover:text-ink"
            }`}
          >
            {label}
            {badges?.[id] && !on && (
              <span
                aria-hidden
                className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-accent"
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
