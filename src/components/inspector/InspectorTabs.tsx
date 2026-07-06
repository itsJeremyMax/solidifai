/**
 * InspectorTabs — the Model · Requirements · Measure · DFM · History · Make
 * segmented control in the Inspector header. The active chip is filled cobalt and
 * shows its label; inactive chips are icon-only on surface-2 (tooltip + aria-label
 * carry the name), which keeps the tabs inside the narrow panel without crowding.
 * Tabs come from the shared {@link INSPECTOR_TABS} registry; `InspectorTab` is
 * re-exported here for existing importers.
 */
import { INSPECTOR_TABS, type InspectorTab } from "./tabs";

export type { InspectorTab };

export default function InspectorTabs({
  active,
  onSelect,
}: {
  active: InspectorTab;
  onSelect: (t: InspectorTab) => void;
}) {
  return (
    <div role="tablist" aria-label="Inspector sections" className="flex gap-1.25">
      {INSPECTOR_TABS.map(({ id, label, Icon }) => {
        const on = active === id;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={on}
            aria-label={label}
            title={label}
            onClick={() => onSelect(id)}
            className={
              on
                ? "inline-flex h-7 items-center gap-1.5 rounded-lg bg-accent px-2.75 text-xs font-semibold text-white"
                : "inline-flex h-7 w-7 items-center justify-center rounded-lg bg-surface-2 text-ink-3 transition-colors hover:text-ink"
            }
          >
            <Icon size={14} strokeWidth={1.9} />
            {on && label}
          </button>
        );
      })}
    </div>
  );
}
