/**
 * Inspector — the right-hand panel. A two-tab shell:
 *   • Model   — collapsible sections: Parts (eye toggles + selection),
 *               Parameters (sliders), Dimensions·Info.
 *   • History — the full-height edit-history list (click a row to restore).
 *
 * Layout prefs (active tab + which sections are open) persist via
 * useInspectorPrefs (localStorage). Selection + per-part visibility are owned by
 * AppShell and flow in as props (selectedId/hiddenIds + callbacks); they default
 * to inert so the panel still renders if a parent doesn't pass them.
 *
 * Parameter sliders keep their optimistic-drag + click-to-edit behavior; commits
 * are single-flight / latest-wins (see useParamCommit / ParamSlider).
 */
import { useState } from "react";
import { ChevronsLeft, ChevronsRight, Eye, EyeOff } from "lucide-react";

import Rail from "./inspector/Rail";
import ParamSlider from "./inspector/ParamSlider";
import History from "./History";
import CollapsibleSection from "./inspector/CollapsibleSection";
import InspectorTabs from "./inspector/InspectorTabs";
import PartsList from "./inspector/PartsList";
import AssemblyTree from "./inspector/AssemblyTree";
import DfmResults from "./inspector/DfmResults";
import MakePanel from "./inspector/MakePanel";
import MeasurePanel from "./inspector/MeasurePanel";
import PlanPanel from "./inspector/PlanPanel";
import RequirementsPanel from "./inspector/RequirementsPanel";
import ExploreSection, { type ExploreParam } from "./inspector/ExploreSection";
import { useInspectorPrefs } from "../state/useInspectorPrefs";
import { useParamCommit } from "../hooks/useParamCommit";
import { useAssemblyMeta } from "../hooks/useAssemblyMeta";
import type { ModelInfo } from "../lib/artifacts";
import { round1 } from "../lib/format";

const EMPTY_IDS: ReadonlySet<string> = new Set<string>();

/* ──────────────────────────────── info row ────────────────────────────── */

/** A key/value info row. `ok` colors the value engine-green; `bad` colors red. */
function InfoRow({
  k,
  v,
  ok = false,
  bad = false,
}: {
  k: string;
  v: string;
  ok?: boolean;
  bad?: boolean;
}) {
  const tone = bad ? "text-danger" : ok ? "text-engine" : "text-ink";
  return (
    <div className="flex justify-between px-3.5 py-1.5 text-xs">
      <span className="text-ink-3">{k}</span>
      <span className={`font-mono ${tone}`}>{v}</span>
    </div>
  );
}

/* ───────────────────────────── show-all / hide-all ────────────────────────── */

function ShowAllToggle({
  anyHidden,
  onToggleAll,
}: {
  anyHidden: boolean;
  onToggleAll: () => void;
}) {
  return (
    <button
      type="button"
      title={anyHidden ? "Show all parts" : "Hide all parts"}
      aria-label={anyHidden ? "Show all parts" : "Hide all parts"}
      onClick={(e) => {
        e.stopPropagation();
        onToggleAll();
      }}
      className="grid h-4.5 w-4.5 place-items-center rounded-sm text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
    >
      {anyHidden ? <EyeOff size={13} strokeWidth={1.8} /> : <Eye size={13} strokeWidth={1.8} />}
    </button>
  );
}

/* ─────────────────────────────── inspector ────────────────────────────── */

interface InspectorProps {
  /** Live render manifest, or null when no build exists yet. */
  model: ModelInfo | null;
  /** Focused-workspace root path; feeds the read-only Plan panel's build brief. */
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
  const commit = useParamCommit(onRefresh, onBuilding);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const { tab, setTab, open, toggleSection } = useInspectorPrefs();

  const objects = model?.objects ?? [];
  // Filter out `explode` — it's a pure viewport transform, not an engine parameter.
  const schemaEntries = model
    ? Object.entries(model.params.schema).filter(([key]) => key !== "explode")
    : [];
  const anyHidden = objects.some((o) => hiddenIds.has(o.id));

  // Assembly metadata (occurrences + joints) enriches the hierarchical tree. Only
  // fetched for a nested assembly (any path id contains "/"); single-model
  // workspaces and older engines return empty and the tree renders unchanged.
  const isAssembly = objects.some((o) => o.id.includes("/"));
  const assembly = useAssemblyMeta(model?.buildId ?? -1, isAssembly);

  return (
    <aside
      className="flex flex-col overflow-hidden border-l border-line bg-surface transition-[flex-basis,width] duration-[340ms] ease-out-soft"
      style={{ width: collapsed ? 54 : 286, flex: `0 0 ${collapsed ? 54 : 286}px` }}
    >
      <div
        className={`flex h-10.5 items-center gap-2 border-b border-line ${
          collapsed ? "justify-center px-0" : "px-2.5"
        }`}
      >
        {!collapsed && <InspectorTabs active={tab} onSelect={setTab} />}
        <button
          type="button"
          onClick={onToggle}
          title={collapsed ? "Expand panel" : "Collapse panel"}
          className={`grid h-7 w-7 place-items-center rounded-lg border border-line-2 bg-surface text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink ${
            collapsed ? "" : "ml-auto"
          }`}
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
      ) : tab === "plan" ? (
        <div className="flex-1 overflow-auto">
          <PlanPanel wsPath={wsPath} />
        </div>
      ) : tab === "history" ? (
        <div className="flex-1 overflow-auto">
          <History />
        </div>
      ) : tab === "requirements" ? (
        <div className="flex-1 overflow-auto">
          <RequirementsPanel
            buildId={model?.buildId ?? -1}
            active={tab === "requirements"}
            hasParams={schemaEntries.length > 0}
          />
        </div>
      ) : tab === "measure" ? (
        <div className="flex-1 overflow-auto">
          <MeasurePanel
            buildId={model?.buildId ?? -1}
            active={tab === "measure"}
            selectedId={selectedId}
            onSelectPart={onSelect}
          />
        </div>
      ) : tab === "dfm" ? (
        <div className="flex-1 overflow-auto">
          <DfmResults
            buildId={model?.buildId ?? -1}
            active={tab === "dfm"}
            selectedId={selectedId}
            onSelectPart={onSelect}
          />
        </div>
      ) : tab === "make" ? (
        <div className="flex-1 overflow-auto">
          <MakePanel buildId={model?.buildId ?? -1} active={tab === "make"} />
        </div>
      ) : (
        <div className="flex-1 overflow-auto">
          <CollapsibleSection
            title="Parts"
            count={objects.length}
            open={open.parts}
            onToggle={() => toggleSection("parts")}
            action={
              objects.length > 0 ? (
                <ShowAllToggle anyHidden={anyHidden} onToggleAll={onToggleAll} />
              ) : undefined
            }
          >
            {model === null ? (
              <div className="px-3.5 pb-2.5 pt-0.5 text-xs text-ink-3">No model yet</div>
            ) : // A nested assembly (any path id contains "/") gets the hierarchical
            // tree; a flat single- or multi-part model keeps the unchanged list.
            isAssembly ? (
              <AssemblyTree
                objects={objects}
                selectedId={selectedId}
                hiddenIds={hiddenIds}
                onSelect={onSelect}
                onToggleVisible={onToggleVisible}
                materialOverrides={materialOverrides}
                onSetPartMaterial={onSetPartMaterial}
                families={assembly.families}
                joints={assembly.joints}
              />
            ) : (
              <PartsList
                objects={objects}
                selectedId={selectedId}
                hiddenIds={hiddenIds}
                onSelect={onSelect}
                onToggleVisible={onToggleVisible}
                materialOverrides={materialOverrides}
                onSetPartMaterial={onSetPartMaterial}
              />
            )}
          </CollapsibleSection>

          <CollapsibleSection
            title="Parameters"
            open={open.parameters}
            onToggle={() => toggleSection("parameters")}
          >
            {schemaEntries.length === 0 ? (
              <div className="px-3.5 pb-2.75 pt-0.5 text-xs text-ink-3">
                {model === null ? "No model yet" : "This model has no adjustable parameters"}
              </div>
            ) : (
              schemaEntries.map(([key, entry]) => (
                <ParamSlider
                  key={key}
                  paramKey={key}
                  entry={entry}
                  value={model!.params.values[key] ?? entry.value}
                  buildId={model!.buildId}
                  onCommit={commit}
                  editing={editingKey === key}
                  onEditOpen={setEditingKey}
                  onEditClose={() => setEditingKey(null)}
                />
              ))
            )}
          </CollapsibleSection>

          <CollapsibleSection
            title="Explore"
            open={open.explore}
            onToggle={() => toggleSection("explore")}
          >
            <ExploreSection
              params={schemaEntries.map(([key, entry]): ExploreParam => ({
                key,
                min: entry.min,
                max: entry.max,
                step: entry.step,
                unit: entry.unit,
              }))}
              currentValues={model?.params.values ?? {}}
              currentSize={model ? (model.bbox.size as [number, number, number]) : undefined}
              onApply={commit}
            />
          </CollapsibleSection>

          <CollapsibleSection
            title="Dimensions · Info"
            open={open.dimensions}
            onToggle={() => toggleSection("dimensions")}
          >
            {model === null ? (
              <div className="px-3.5 pb-3.5 pt-0.5 text-xs text-ink-3">No model yet</div>
            ) : (
              <>
                <InfoRow
                  k="Bounding box"
                  v={`${round1(model.bbox.size[0])}×${round1(model.bbox.size[1])}×${round1(
                    model.bbox.size[2],
                  )}`}
                />
                <InfoRow k="Volume" v={`${(model.volume / 1000).toFixed(2)} cm³`} />
                <InfoRow
                  k={`Mass · ${model.mass.material}`}
                  v={`${model.mass.value.toFixed(1)} g`}
                />
                <InfoRow
                  k="Watertight"
                  v={model.manifold ? "✓ yes" : "✗ no"}
                  ok={model.manifold}
                  bad={!model.manifold}
                />
                <InfoRow
                  k="Valid"
                  v={model.valid ? "✓ yes" : "✗ no"}
                  ok={model.valid}
                  bad={!model.valid}
                />
              </>
            )}
          </CollapsibleSection>
        </div>
      )}
    </aside>
  );
}
