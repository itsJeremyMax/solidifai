/**
 * ModelPanel — the Inspector's Model tab: Parts, Parameters, Explore, Measure.
 * Section open-state persists via useInspectorPrefs ("model.*") and flows in
 * as props.
 */
import { Eye, EyeOff } from "lucide-react";

import CollapsibleSection from "./CollapsibleSection";
import ParamSlider from "./ParamSlider";
import PartsList from "./PartsList";
import AssemblyTree from "./AssemblyTree";
import ExploreSection, { type ExploreParam } from "./ExploreSection";
import MeasureSection from "./MeasureSection";
import { useParamCommit } from "../../hooks/useParamCommit";
import { useAssemblyMeta } from "../../hooks/useAssemblyMeta";
import type { SectionKey, SectionState } from "../../state/useInspectorPrefs";
import type { ModelInfo } from "../../lib/artifacts";
import type { Material } from "../../lib/materials";
import { useState } from "react";

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

export default function ModelPanel({
  model,
  active,
  onRefresh,
  onBuilding,
  open,
  onToggleSection,
  selectedId,
  hiddenIds,
  onSelect,
  onToggleVisible,
  onToggleAll,
  materialOverrides,
  onSetPartMaterial,
}: {
  model: ModelInfo | null;
  active: boolean;
  onRefresh: () => Promise<void>;
  onBuilding: (building: boolean) => void;
  open: SectionState;
  onToggleSection: (k: SectionKey) => void;
  selectedId: string | null;
  hiddenIds: ReadonlySet<string>;
  onSelect: (id: string | null) => void;
  onToggleVisible: (id: string) => void;
  onToggleAll: () => void;
  materialOverrides: Record<string, Material>;
  onSetPartMaterial: (partId: string, material: Material | null) => void;
}) {
  const commit = useParamCommit(onRefresh, onBuilding);
  const [editingKey, setEditingKey] = useState<string | null>(null);

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
    <>
      {/* Parameters lead: the sliders are what a user edits most. */}
      <CollapsibleSection
        title="Parameters"
        count={schemaEntries.length || undefined}
        open={open["model.parameters"]}
        onToggle={() => onToggleSection("model.parameters")}
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
        title="Parts"
        count={objects.length}
        open={open["model.parts"]}
        onToggle={() => onToggleSection("model.parts")}
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
        title="Measure"
        open={open["model.measure"]}
        onToggle={() => onToggleSection("model.measure")}
      >
        <MeasureSection
          model={model}
          active={active && open["model.measure"]}
          selectedId={selectedId}
          onSelectPart={onSelect}
        />
      </CollapsibleSection>

      <CollapsibleSection
        title="Explore"
        open={open["model.explore"]}
        onToggle={() => onToggleSection("model.explore")}
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
    </>
  );
}
