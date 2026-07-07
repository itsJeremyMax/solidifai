import { Settings as SettingsIcon } from "lucide-react";

import HelpMenu from "./HelpMenu";

/** Shared lucide stroke weight to match the design language. */
const ICON_STROKE = 1.7;

/**
 * UtilityCluster — the app-level utility pair (Settings + Help) as one segmented
 * icon control, shared by the home header and the editor TopBar so both surfaces
 * read the same. Settings' destination differs by surface (global vs workspace
 * scope), so it comes in as a callback; Help navigates to global routes itself.
 *
 * The container intentionally does not clip overflow: the Help dropdown escapes
 * it. The end cells are rounded to match the container so their hover fill stays
 * inside the border.
 */
export default function UtilityCluster({ onOpenSettings }: { onOpenSettings: () => void }) {
  return (
    <div className="flex h-8 shrink-0 items-stretch divide-x divide-line-2 rounded-lg border border-line-2 bg-surface">
      <button
        type="button"
        onClick={onOpenSettings}
        title="Settings"
        aria-label="Settings"
        className="grid h-full w-9 place-items-center rounded-l-lg text-ink-2 transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
      >
        <SettingsIcon size={16} strokeWidth={ICON_STROKE} />
      </button>
      <HelpMenu triggerClassName="grid h-full w-9 place-items-center rounded-r-lg text-ink-2 transition-colors duration-150 hover:bg-surface-2 hover:text-ink" />
    </div>
  );
}
