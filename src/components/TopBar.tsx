import { BookMarked, Factory, SwatchBook } from "lucide-react";

import EngineStatusPill from "./EngineStatusPill";
import UtilityCluster from "./UtilityCluster";
import { useHeaderSlot } from "../state/headerSlot";

/** Shared lucide stroke weight to match the design language. */
const ICON_STROKE = 1.7;

/**
 * One cell of the segmented icon group (the grouped app destinations). The cell
 * is borderless and square; the segment container draws the shared border and
 * the hairline dividers between cells.
 */
function SegButton({
  icon,
  title,
  onClick,
}: {
  icon: React.ReactNode;
  title: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      className="grid h-full w-9 place-items-center text-ink-2 transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
    >
      {icon}
    </button>
  );
}

interface TopBarProps {
  /** Open the settings page (workspace scope). */
  onOpenSettings: () => void;
  /** Open the materials library (workspace scope). */
  onOpenMaterials?: () => void;
  /** Open the Factory page (app-level connections). */
  onOpenFactory?: () => void;
  /** Open the References library (workspace scope). */
  onOpenReferences?: () => void;
}

/**
 * TopBar — publishes the app-level controls into the persistent AppHeader actions
 * slot. Workspace identity + per-tab engine readiness live in the header's
 * WorkspaceSwitcher (left); the per-workspace document verbs (Measure/Import/
 * Drawing/Export) live in WorkspaceToolbar, which renders inside the active
 * session below the header (Option B). The EngineStatusPill stays here for the
 * focused engine's version string and the GLOBAL engine-update progress (the
 * `updating` state), which the per-tab switcher dots do not cover.
 */
export default function TopBar({
  onOpenSettings,
  onOpenMaterials,
  onOpenFactory,
  onOpenReferences,
}: TopBarProps) {
  useHeaderSlot({
    actions: (
      <>
        <EngineStatusPill />

        {/* Hairline that separates the status zone from the controls. */}
        <span className="h-5 w-px shrink-0 bg-line-2" />

        {/* Libraries, grouped as one segmented icon control (tooltips name each).
            Conditional members collapse without leaving stray dividers. */}
        {(onOpenMaterials || onOpenFactory || onOpenReferences) && (
          <div className="flex h-8 shrink-0 items-stretch divide-x divide-line-2 overflow-hidden rounded-lg border border-line-2 bg-surface">
            {onOpenMaterials && (
              <SegButton
                title="Materials"
                icon={<SwatchBook size={16} strokeWidth={ICON_STROKE} />}
                onClick={onOpenMaterials}
              />
            )}
            {onOpenFactory && (
              <SegButton
                title="Factory"
                icon={<Factory size={16} strokeWidth={ICON_STROKE} />}
                onClick={onOpenFactory}
              />
            )}
            {onOpenReferences && (
              <SegButton
                title="References"
                icon={<BookMarked size={16} strokeWidth={ICON_STROKE} />}
                onClick={onOpenReferences}
              />
            )}
          </div>
        )}

        {/* App utilities — Settings + Help as one segmented pair. */}
        <UtilityCluster onOpenSettings={onOpenSettings} />
      </>
    ),
  });
  return null;
}
