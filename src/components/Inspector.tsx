/**
 * Inspector — the right-hand panel. Four tabs (Model · Checks · Activity ·
 * Make) in a fixed-geometry segmented control; section layout persists via
 * useInspectorPrefs. Selection + per-part visibility are owned by AppShell and
 * flow in as props; they default to inert so the panel still renders if a
 * parent doesn't pass them.
 */
import { useEffect, useRef, useState } from "react";
import { ChevronsLeft, ChevronsRight } from "lucide-react";

import Rail from "./inspector/Rail";
import InspectorTabs from "./inspector/InspectorTabs";
import ModelPanel from "./inspector/ModelPanel";
import ChecksPanel from "./inspector/ChecksPanel";
import ActivityPanel from "./inspector/ActivityPanel";
import MakePanel from "./inspector/MakePanel";
import { useInspectorPrefs } from "../state/useInspectorPrefs";
import { useBuildBrief } from "../hooks/useBuildBrief";
import type { ModelInfo } from "../lib/artifacts";

const EMPTY_IDS: ReadonlySet<string> = new Set<string>();

interface InspectorProps {
  /** Live render manifest, or null when no build exists yet. */
  model: ModelInfo | null;
  /** Focused-workspace root path; feeds the read-only build brief. */
  wsPath: string;
  /** Re-read artifacts after a param commit so the viewport follows the build. */
  onRefresh?: () => Promise<void>;
  collapsed: boolean;
  onToggle: () => void;
  /** Selection + visibility (owned by AppShell). Default inert. */
  selectedId?: string | null;
  hiddenIds?: ReadonlySet<string>;
  /** Selection handler; `null` clears the selection (re-click to deselect). */
  onSelect?: (id: string | null) => void;
  onToggleVisible?: (id: string) => void;
  onToggleAll?: () => void;
  materialOverrides?: Record<string, import("../lib/materials").Material>;
  onSetPartMaterial?: (
    partId: string,
    material: import("../lib/materials").Material | null,
  ) => void;
  onBuilding?: (building: boolean) => void;
}

const NOOP_REFRESH = async () => {};

export default function Inspector({
  model,
  wsPath,
  onRefresh = NOOP_REFRESH,
  collapsed,
  onToggle,
  selectedId = null,
  hiddenIds = EMPTY_IDS,
  onSelect = () => {},
  onToggleVisible = () => {},
  onToggleAll = () => {},
  materialOverrides = {},
  onSetPartMaterial = () => {},
  onBuilding = () => {},
}: InspectorProps) {
  const { tab, setTab, open, toggleSection } = useInspectorPrefs();

  const buildId = model?.buildId ?? -1;
  const hasParams = model
    ? Object.keys(model.params.schema).some((key) => key !== "explode")
    : false;

  // A brief published while the Activity tab is out of view earns a quiet dot
  // on its tab. `rev` bumps only on live updates, so an existing brief loading
  // at startup never badges.
  const { brief, rev: briefRev } = useBuildBrief(wsPath);
  const seenRev = useRef(0);
  const [briefUnseen, setBriefUnseen] = useState(false);
  useEffect(() => {
    if (briefRev > seenRev.current) {
      seenRev.current = briefRev;
      if (tab !== "activity" && brief !== null) setBriefUnseen(true);
    }
  }, [briefRev, tab, brief]);
  useEffect(() => {
    if (tab === "activity" && !collapsed) setBriefUnseen(false);
  }, [tab, collapsed]);

  const visible = collapsed ? null : tab;

  return (
    <aside
      className="flex flex-col overflow-hidden border-l border-line bg-surface transition-[flex-basis,width] duration-[340ms] ease-out-soft"
      style={{ width: collapsed ? 54 : 286, flex: `0 0 ${collapsed ? 54 : 286}px` }}
    >
      <div
        className={`flex h-10.5 shrink-0 items-center gap-2 border-b border-line ${
          collapsed ? "justify-center px-0" : "px-2.5"
        }`}
      >
        {!collapsed && (
          <InspectorTabs active={tab} onSelect={setTab} badges={{ activity: briefUnseen }} />
        )}
        <button
          type="button"
          onClick={onToggle}
          title={collapsed ? "Expand panel" : "Collapse panel"}
          className="grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-line-2 bg-surface text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink"
        >
          {collapsed ? (
            <ChevronsLeft size={15} strokeWidth={1.8} />
          ) : (
            <ChevronsRight size={15} strokeWidth={1.8} />
          )}
        </button>
      </div>

      {collapsed ? (
        <Rail
          activeTab={tab}
          onExpand={(t) => {
            setTab(t);
            onToggle();
          }}
        />
      ) : (
        <div className="flex-1 overflow-auto">
          {visible === "model" && (
            <ModelPanel
              model={model}
              active
              onRefresh={onRefresh}
              onBuilding={onBuilding}
              open={open}
              onToggleSection={toggleSection}
              selectedId={selectedId}
              hiddenIds={hiddenIds}
              onSelect={onSelect}
              onToggleVisible={onToggleVisible}
              onToggleAll={onToggleAll}
              materialOverrides={materialOverrides}
              onSetPartMaterial={onSetPartMaterial}
            />
          )}
          {visible === "checks" && (
            <ChecksPanel
              buildId={buildId}
              active
              hasParams={hasParams}
              selectedId={selectedId}
              onSelectPart={onSelect}
              open={open}
              onToggleSection={toggleSection}
            />
          )}
          {visible === "activity" && (
            <ActivityPanel brief={brief} open={open} onToggleSection={toggleSection} />
          )}
          {visible === "make" && (
            <MakePanel buildId={buildId} active open={open} onToggleSection={toggleSection} />
          )}
        </div>
      )}
    </aside>
  );
}
