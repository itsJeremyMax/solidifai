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
import Select from "../ui/Select";
import { useParamCommit } from "../../hooks/useParamCommit";
import { useAssemblyMeta } from "../../hooks/useAssemblyMeta";
import type { SectionKey, SectionState } from "../../state/useInspectorPrefs";
import {
  isBooleanParamSchemaEntry,
  isEnumParamSchemaEntry,
  isNumericParamSchemaEntry,
  type ModelInfo,
  type NumericParamSchemaEntry,
  type ParamSchemaEntry,
  type ParamValue,
} from "../../lib/artifacts";
import type { Material } from "../../lib/materials";
import { useEffect, useRef, useState } from "react";

function titleCase(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .trim()
    .split(/\s+/)
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : word))
    .join(" ");
}

function isNumericSchemaEntry(
  entry: [string, ParamSchemaEntry],
): entry is [string, NumericParamSchemaEntry] {
  return isNumericParamSchemaEntry(entry[1]);
}

function useOptimisticParamValue<T extends boolean | string>(
  value: T,
  onCommit: (key: string, value: ParamValue, onError?: (error: unknown) => void) => void,
  paramKey: string,
): [T, (next: T) => void] {
  const [local, setLocal] = useState<T>(value);
  const committedRef = useRef(value);
  const localRef = useRef(value);
  const pendingAckRef = useRef(false);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (pendingAckRef.current) {
      if (!Object.is(value, localRef.current)) return;
      pendingAckRef.current = false;
    }
    committedRef.current = value;
    localRef.current = value;
    setLocal(value);
  }, [value]);

  const commitLocal = (next: T) => {
    localRef.current = next;
    pendingAckRef.current = true;
    setLocal(next);
    const requestId = ++requestIdRef.current;
    onCommit(paramKey, next, () => {
      if (requestId !== requestIdRef.current) return;
      pendingAckRef.current = false;
      localRef.current = committedRef.current;
      setLocal(committedRef.current);
    });
  };

  return [local, commitLocal];
}

function ParamBooleanRow({
  paramKey,
  entry,
  value,
  onCommit,
}: {
  paramKey: string;
  entry: Extract<ParamSchemaEntry, { type: "boolean" }>;
  value: boolean;
  onCommit: (key: string, value: ParamValue, onError?: (error: unknown) => void) => void;
}) {
  const [local, commitLocal] = useOptimisticParamValue(value, onCommit, paramKey);
  const hasDesc = entry.desc.trim().length > 0;
  const descId = `param-desc-${paramKey}`;

  return (
    <div className="flex items-start justify-between gap-4 px-3.5 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium text-ink-2">{titleCase(paramKey)}</div>
        {hasDesc && (
          <p id={descId} className="mt-0.5 text-caption leading-snug text-ink-3">
            {entry.desc.trim()}
          </p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={local}
        aria-label={titleCase(paramKey)}
        aria-describedby={hasDesc ? descId : undefined}
        onClick={() => commitLocal(!local)}
        className={`relative mt-0.25 inline-flex h-5.5 w-9.5 shrink-0 items-center rounded-full outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent-tint ${
          local ? "bg-accent" : "bg-line-2 hover:bg-[rgba(18,20,28,.2)]"
        }`}
      >
        <span
          className={`inline-block h-4 w-4 rounded-full bg-surface shadow-[0_1px_2px_rgba(16,18,24,.28)] transition-transform duration-150 ${
            local ? "translate-x-4.75" : "translate-x-0.75"
          }`}
        />
      </button>
    </div>
  );
}

function ParamEnumRow({
  paramKey,
  entry,
  value,
  onCommit,
}: {
  paramKey: string;
  entry: Extract<ParamSchemaEntry, { type: "enum" }>;
  value: string;
  onCommit: (key: string, value: ParamValue, onError?: (error: unknown) => void) => void;
}) {
  const [local, commitLocal] = useOptimisticParamValue(value, onCommit, paramKey);
  const hasDesc = entry.desc.trim().length > 0;
  const descId = `param-desc-${paramKey}`;

  return (
    <div className="px-3.5 py-2.5">
      <div className="mb-2 min-w-0">
        <div className="text-xs font-medium text-ink-2">{titleCase(paramKey)}</div>
        {hasDesc && (
          <p id={descId} className="mt-0.5 text-caption leading-snug text-ink-3">
            {entry.desc.trim()}
          </p>
        )}
      </div>
      <Select
        value={local}
        onChange={commitLocal}
        ariaLabel={titleCase(paramKey)}
        ariaDescribedBy={hasDesc ? descId : undefined}
        options={entry.choices.map((choice) => ({ value: choice, label: choice }))}
      />
    </div>
  );
}

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
  const exploreParams = schemaEntries.filter(isNumericSchemaEntry);
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
          schemaEntries.map(([key, entry]) => {
            const value = model!.params.values[key] ?? entry.value;
            if (isNumericParamSchemaEntry(entry) && typeof value === "number") {
              return (
                <ParamSlider
                  key={key}
                  paramKey={key}
                  entry={entry}
                  value={value}
                  buildId={model!.buildId}
                  onCommit={commit}
                  editing={editingKey === key}
                  onEditOpen={setEditingKey}
                  onEditClose={() => setEditingKey(null)}
                />
              );
            }
            if (isBooleanParamSchemaEntry(entry) && typeof value === "boolean") {
              return (
                <ParamBooleanRow
                  key={key}
                  paramKey={key}
                  entry={entry}
                  value={value}
                  onCommit={commit}
                />
              );
            }
            if (isEnumParamSchemaEntry(entry) && typeof value === "string") {
              return (
                <ParamEnumRow
                  key={key}
                  paramKey={key}
                  entry={entry}
                  value={value}
                  onCommit={commit}
                />
              );
            }
            return null;
          })
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
          params={exploreParams.map(([key, entry]): ExploreParam => ({
            key,
            min: entry.min,
            max: entry.max,
            step: entry.step,
            unit: entry.unit,
          }))}
          currentValues={
            Object.fromEntries(
              exploreParams
                .map(([key]) => [key, model?.params.values[key]])
                .filter(([, value]) => typeof value === "number"),
            ) as Record<string, number>
          }
          currentSize={model?.bbox?.size as [number, number, number] | undefined}
          onApply={commit}
        />
      </CollapsibleSection>
    </>
  );
}
