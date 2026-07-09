/**
 * AssemblyTree — the Model tab's Parts rows for a nested assembly. Phase 2A
 * renders each leaf with a slash-separated path id (e.g. "hinge/pin"), so the
 * hierarchy is derived client-side (buildAssemblyTree) with no engine call.
 *
 * This is the hierarchical sibling of PartsList: it reuses PartsList's exact row
 * chrome (row height, selection tint + inset accent bar, hover, visibility eye,
 * material swatch) so a leaf row reads identically. The one new affordance is a
 * leading disclosure chevron on group nodes (expand/collapse); leaf rows get a
 * matching spacer so labels stay aligned. Rows indent by depth.
 *
 * Selecting a group selects its path-prefix id; the viewport resolves that to
 * every descendant subtree (see subtreeIndicesForId in useThreeScene). The eye
 * and material swatch on a group act on every descendant leaf, since visibility
 * and materials are keyed per leaf id. The single-part / flat case still works
 * (a one-node tree), though Inspector only mounts this when an id contains "/".
 */
import { useState } from "react";
import { ChevronRight, Eye, EyeOff } from "lucide-react";

import type { ModelObject } from "../../lib/artifacts";
import type { Material } from "../../lib/materials";
import { buildAssemblyTree, descendantIds, type TreeNode } from "../../lib/assemblyTree";
import type { JointInfo, OccurrenceFamily, OccurrenceInfo } from "../../lib/assemblyMeta";
import PartMaterialPicker from "./PartMaterialPicker";

/** sRGB gamma encode a single linear channel (0..1). */
function linearToSrgb(c: number): number {
  const v = c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
  return Math.max(0, Math.min(255, Math.round(v * 255)));
}

/** Linear-RGB triple (0..1, as the engine resolves it) -> `#rrggbb`. */
function linearRgbToHex([r, g, b]: readonly [number, number, number]): string {
  const h = (n: number) => linearToSrgb(n).toString(16).padStart(2, "0");
  return `#${h(r)}${h(g)}${h(b)}`;
}

/** Leading indent per depth level (rem). Matches the row's gap-2.25 rhythm. */
const INDENT_REM = 0.9375; // 15px, the chevron column width

export interface AssemblyTreeProps {
  objects: ModelObject[];
  selectedId: string | null;
  hiddenIds: ReadonlySet<string>;
  onSelect: (id: string | null) => void;
  onToggleVisible: (id: string) => void;
  materialOverrides?: Record<string, Material>;
  onSetPartMaterial?: (partId: string, material: Material | null) => void;
  /** Occurrence families (from `get_assembly_tree`), keyed by primary path id.
   *  Instanced parts fold into a single badged row; absent for single-model or
   *  pre-protocol-11 engines (the tree renders unchanged). */
  families?: Map<string, OccurrenceFamily>;
  /** Skeleton joints to list below the tree; empty when the assembly has none. */
  joints?: JointInfo[];
}

export default function AssemblyTree({
  objects,
  selectedId,
  hiddenIds,
  onSelect,
  onToggleVisible,
  materialOverrides = {},
  onSetPartMaterial = () => {},
  families,
  joints = [],
}: AssemblyTreeProps) {
  const tree = buildAssemblyTree(objects, families);
  // Path ids of groups the user collapsed; everything is expanded by default.
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set());
  // Occurrence families the user expanded to see the frame list (collapsed by
  // default, so an instanced part reads as one badged row until asked).
  const [openOcc, setOpenOcc] = useState<ReadonlySet<string>>(() => new Set());
  // Open material picker, anchored to the row swatch. `id` is a leaf or group id.
  const [picker, setPicker] = useState<{ id: string; anchor: DOMRect } | null>(null);

  const byId = new Map(objects.map((o) => [o.id, o] as const));

  if (objects.length === 0) {
    return <div className="px-3.5 pb-2.5 pt-0.5 text-xs text-ink-3">Empty model</div>;
  }

  const toggleCollapsed = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggleOpenOcc = (id: string) =>
    setOpenOcc((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // Swatch tint for a leaf: optimistic override wins, else resolved appearance,
  // else neutral grey (older artifacts with no appearance). Mirrors PartsList.
  const leafSwatchHex = (obj: ModelObject): string => {
    const overridden = materialOverrides[obj.id];
    if (overridden) return overridden.colorHex;
    return obj.appearance ? linearRgbToHex(obj.appearance.baseColor) : "#9aa0aa";
  };

  // A group shows a single tint only when every descendant resolves to the same
  // color; otherwise it reads neutral (a mixed selection has no one color).
  const groupSwatchHex = (leafIds: string[]): string => {
    const hexes = new Set(leafIds.map((id) => (byId.has(id) ? leafSwatchHex(byId.get(id)!) : "")));
    return hexes.size === 1 ? [...hexes][0] : "#9aa0aa";
  };

  // The picker's "current material" for a group: the shared id, else undefined.
  const groupCurrentMaterialId = (leafIds: string[]): string | undefined => {
    const ids = new Set(
      leafIds.map((id) => materialOverrides[id]?.id ?? byId.get(id)?.appearance?.material),
    );
    return ids.size === 1 ? [...ids][0] : undefined;
  };

  const renderNode = (node: TreeNode, depth: number): React.ReactNode => {
    const selected = node.id === selectedId;
    const indent = { paddingLeft: `${0.875 + depth * INDENT_REM}rem` }; // 0.875rem = px-3.5

    // Instanced part: one definition placed N times. Renders as a single badged
    // row; the eye/swatch/selection act on every placement (occLeafIds). Expand
    // to read the frame list. `occurrences` is only set by the family merge.
    if (node.occurrences) {
      const leafIds = node.occLeafIds ?? [];
      const allHidden = leafIds.length > 0 && leafIds.every((id) => hiddenIds.has(id));
      const isOpen = openOcc.has(node.id);
      const swatchHex = groupSwatchHex(leafIds);
      const n = node.occurrences.length;
      return (
        <div key={node.id}>
          <Row
            label={node.label}
            depthStyle={indent}
            selected={selected}
            hidden={allHidden}
            leading={
              <button
                type="button"
                title={isOpen ? "Hide placements" : "Show placements"}
                aria-label={
                  isOpen ? `Hide ${node.label} placements` : `Show ${node.label} placements`
                }
                aria-expanded={isOpen}
                onClick={(e) => {
                  e.stopPropagation();
                  toggleOpenOcc(node.id);
                }}
                className="grid h-3.75 w-3.75 shrink-0 place-items-center rounded-sm text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
              >
                <ChevronRight
                  size={13}
                  strokeWidth={2}
                  className={`transition-transform ${isOpen ? "rotate-90" : ""}`}
                  aria-hidden
                />
              </button>
            }
            marker={
              <span
                className={
                  selected
                    ? "h-3.75 w-3.75 shrink-0 rounded-sm border-[1.5px] border-accent bg-accent-tint"
                    : `h-3.75 w-3.75 shrink-0 rounded-sm border-[1.5px] ${
                        allHidden ? "border-line-2" : "border-ink-3"
                      }`
                }
              />
            }
            trailingLabel={<OccurrenceBadge n={n} />}
            onSelect={() => onSelect(selected ? null : node.id)}
            swatchHex={swatchHex}
            swatchHidden={allHidden}
            onOpenPicker={(anchor) => setPicker({ id: node.id, anchor })}
            label2={node.label}
            onToggleVisible={() => {
              const target = !allHidden; // true = hide, false = show
              for (const id of leafIds) {
                if (hiddenIds.has(id) !== target) onToggleVisible(id);
              }
            }}
            visForcedHidden={allHidden}
          />
          {isOpen &&
            node.occurrences.map((occ, i) => (
              <OccurrenceRow
                key={`${node.id}#${i}`}
                occ={occ}
                depthStyle={{ paddingLeft: `${0.875 + (depth + 1) * INDENT_REM}rem` }}
              />
            ))}
        </div>
      );
    }

    if (node.isLeaf && node.children.length === 0) {
      // Leaf row: identical to a PartsList row, indented and label = leaf segment.
      const obj = byId.get(node.id);
      const hidden = hiddenIds.has(node.id);
      const swatchHex = obj ? leafSwatchHex(obj) : "#9aa0aa";
      return (
        <div key={node.id}>
          <Row
            label={node.label}
            depthStyle={indent}
            selected={selected}
            hidden={hidden}
            leading={<span className="w-3.75 shrink-0" aria-hidden />}
            marker={
              <span
                className={
                  selected
                    ? "h-3.75 w-3.75 shrink-0 rounded-sm border-[1.5px] border-accent bg-accent-tint"
                    : `h-3.75 w-3.75 shrink-0 rounded-sm border-[1.5px] ${
                        hidden ? "border-line-2" : "border-ink-3"
                      }`
                }
              />
            }
            trailingLabel={
              <span className="ml-auto shrink-0 font-mono text-caption text-ink-3">
                {obj?.kind || "Part"}
              </span>
            }
            onSelect={() => onSelect(selected ? null : node.id)}
            swatchHex={swatchHex}
            swatchHidden={hidden}
            onOpenPicker={(anchor) => setPicker({ id: node.id, anchor })}
            label2={node.label}
            onToggleVisible={() => onToggleVisible(node.id)}
          />
        </div>
      );
    }

    // Group row. Visibility/material span all descendant leaves.
    const leafIds = descendantIds(tree, node.id);
    const allHidden = leafIds.length > 0 && leafIds.every((id) => hiddenIds.has(id));
    const isCollapsed = collapsed.has(node.id);
    const swatchHex = groupSwatchHex(leafIds);

    return (
      <div key={node.id}>
        <Row
          label={node.label}
          depthStyle={indent}
          selected={selected}
          hidden={allHidden}
          leading={
            <button
              type="button"
              title={isCollapsed ? "Expand group" : "Collapse group"}
              aria-label={isCollapsed ? `Expand ${node.label}` : `Collapse ${node.label}`}
              aria-expanded={!isCollapsed}
              onClick={(e) => {
                e.stopPropagation();
                toggleCollapsed(node.id);
              }}
              className="grid h-3.75 w-3.75 shrink-0 place-items-center rounded-sm text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
            >
              <ChevronRight
                size={13}
                strokeWidth={2}
                className={`transition-transform ${isCollapsed ? "" : "rotate-90"}`}
                aria-hidden
              />
            </button>
          }
          marker={
            <span
              className={
                selected
                  ? "h-3.75 w-3.75 shrink-0 rounded-sm border-[1.5px] border-accent bg-accent-tint"
                  : `h-3.75 w-3.75 shrink-0 rounded-sm border-[1.5px] ${
                      allHidden ? "border-line-2" : "border-ink-3"
                    }`
              }
            />
          }
          trailingLabel={
            <span className="ml-auto shrink-0 font-mono text-caption text-ink-3">
              {leafIds.length} {leafIds.length === 1 ? "part" : "parts"}
            </span>
          }
          onSelect={() => onSelect(selected ? null : node.id)}
          swatchHex={swatchHex}
          swatchHidden={allHidden}
          onOpenPicker={(anchor) => setPicker({ id: node.id, anchor })}
          label2={node.label}
          onToggleVisible={() => {
            // The group eye reads "Hide" until every descendant is hidden, then
            // "Show". So a click hides all currently-visible leaves; once all are
            // hidden the next click shows them all. Only flip leaves not already
            // at the target state.
            const target = !allHidden; // true = hide, false = show
            for (const id of leafIds) {
              if (hiddenIds.has(id) !== target) onToggleVisible(id);
            }
          }}
          visForcedHidden={allHidden}
        />
        {!isCollapsed && node.children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  };

  // Resolve the open picker's anchor object (leaf or group) to its current id +
  // the leaf ids it should write to.
  const pickerLeafIds = picker
    ? byId.has(picker.id)
      ? [picker.id]
      : descendantIds(tree, picker.id)
    : [];
  const pickerCurrentId = picker
    ? byId.has(picker.id)
      ? (materialOverrides[picker.id]?.id ?? byId.get(picker.id)?.appearance?.material)
      : groupCurrentMaterialId(pickerLeafIds)
    : undefined;

  return (
    <div className="pb-1">
      {tree.map((node) => renderNode(node, 0))}

      {joints.length > 0 && <JointsSection joints={joints} />}

      {picker && pickerLeafIds.length > 0 && (
        <PartMaterialPicker
          anchor={picker.anchor}
          currentMaterialId={pickerCurrentId}
          onPick={(material) => {
            for (const id of pickerLeafIds) onSetPartMaterial(id, material);
            setPicker(null);
          }}
          onClearToDefault={() => {
            for (const id of pickerLeafIds) onSetPartMaterial(id, null);
            setPicker(null);
          }}
          onClose={() => setPicker(null)}
        />
      )}
    </div>
  );
}

/**
 * The `×N` multiplicity badge on an instanced part. Sits in the row's trailing
 * slot where a plain part shows its kind. Quiet by design: the count is the
 * signal, not the chrome.
 */
function OccurrenceBadge({ n }: { n: number }) {
  return (
    <span
      className="ml-auto shrink-0 rounded-full border border-line-2 px-1.5 py-0.25 font-mono text-caption text-ink-2"
      title={`Placed ${n} times`}
    >
      ×{n}
    </span>
  );
}

/**
 * One placement under an expanded instanced part: its display id (wheel@2), the
 * frame it sits at, and a mirror tag when the copy is reflected. Read-only.
 */
function OccurrenceRow({
  occ,
  depthStyle,
}: {
  occ: OccurrenceInfo;
  depthStyle: React.CSSProperties;
}) {
  return (
    <div
      style={depthStyle}
      className="flex items-center gap-2.25 py-1 pr-3.5 text-caption text-ink-3"
    >
      <span className="w-3.75 shrink-0" aria-hidden />
      <span className="shrink-0 font-mono text-ink-2">{occ.label}</span>
      <span className="truncate">{occ.frame ? `at ${occ.frame}` : "at origin"}</span>
      {occ.mirror && (
        <span
          className="ml-auto shrink-0 rounded-full bg-surface-2 px-1.5 font-mono text-ink-3"
          title={`Mirrored about the ${occ.mirror} plane`}
        >
          mirror {occ.mirror}
        </span>
      )}
    </div>
  );
}

/**
 * The skeleton's declared joints, listed below the tree. Read-only: each row
 * shows the joint's name, kind, driven frame, travel limits, and the two parts
 * it sits between. The agent declares and drives these over MCP; the panel just
 * reflects them.
 */
function JointsSection({ joints }: { joints: JointInfo[] }) {
  return (
    <div className="mt-1 border-t border-line pt-1.5">
      <div className="px-3.5 pb-1 pt-0.5 text-caption font-medium uppercase tracking-wide text-ink-3">
        Joints
      </div>
      {joints.map((j) => (
        <JointRow key={j.displayName} joint={j} />
      ))}
    </div>
  );
}

/** One joint: name + kind pill, then its frame/limits/between as compact meta. */
function JointRow({ joint }: { joint: JointInfo }) {
  const meta: string[] = [];
  if (joint.frame) meta.push(`frame ${joint.frame}`);
  if (joint.limits) meta.push(`limits ${joint.limits[0]} to ${joint.limits[1]}`);
  if (joint.between && joint.between.length > 0) meta.push(joint.between.join(" ↔ "));
  return (
    <div className="px-3.5 py-1.5">
      <div className="flex items-center gap-2">
        <span className="truncate text-body text-ink">{joint.displayName}</span>
        <span className="shrink-0 rounded-full border border-line-2 px-1.5 text-caption text-ink-2">
          {joint.kind}
        </span>
      </div>
      {meta.length > 0 && (
        <div className="mt-0.5 font-mono text-caption text-ink-3">{meta.join("  ·  ")}</div>
      )}
    </div>
  );
}

/**
 * One assembly row. Shares PartsList's row chrome exactly; the only structural
 * addition over a flat list is the `leading` slot (a chevron for groups, a
 * spacer for leaves) and depth indent via `depthStyle`.
 */
function Row({
  label,
  depthStyle,
  selected,
  hidden,
  leading,
  marker,
  trailingLabel,
  onSelect,
  swatchHex,
  swatchHidden,
  onOpenPicker,
  label2,
  onToggleVisible,
  visForcedHidden,
}: {
  label: string;
  depthStyle: React.CSSProperties;
  selected: boolean;
  hidden: boolean;
  leading: React.ReactNode;
  marker: React.ReactNode;
  trailingLabel: React.ReactNode;
  onSelect: () => void;
  swatchHex: string;
  swatchHidden: boolean;
  onOpenPicker: (anchor: DOMRect) => void;
  label2: string;
  onToggleVisible: () => void;
  visForcedHidden?: boolean;
}) {
  const eyeHidden = visForcedHidden ?? hidden;
  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      style={depthStyle}
      className={
        selected
          ? "flex cursor-pointer items-center gap-2.25 bg-accent-tint py-1.75 pr-3.5 text-body shadow-[inset_2px_0_0_var(--color-accent)]"
          : "flex cursor-pointer items-center gap-2.25 py-1.75 pr-3.5 text-body hover:bg-surface-2"
      }
    >
      {leading}
      {marker}
      <span className={`truncate ${hidden ? "text-ink-3" : ""}`}>{label}</span>
      {trailingLabel}
      <button
        type="button"
        title="Assign material"
        aria-label={`Material for ${label2}`}
        onClick={(e) => {
          e.stopPropagation();
          onOpenPicker(e.currentTarget.getBoundingClientRect());
        }}
        className={`grid h-4.5 w-4.5 shrink-0 place-items-center rounded-sm transition-colors hover:bg-surface-2 ${
          swatchHidden ? "opacity-55" : ""
        }`}
      >
        <span
          aria-hidden
          className="h-3.25 w-3.25 rounded-full ring-1 ring-inset ring-[rgba(18,20,28,.18)] shadow-[inset_0_-2px_3px_rgba(8,10,18,.28),inset_0_1px_2px_rgba(255,255,255,.3)]"
          style={{
            background: `radial-gradient(circle at 34% 30%, color-mix(in srgb, ${swatchHex}, white 62%) 0%, transparent 52%), ${swatchHex}`,
          }}
        />
      </button>
      <button
        type="button"
        title={eyeHidden ? "Show" : "Hide"}
        aria-label={eyeHidden ? `Show ${label2}` : `Hide ${label2}`}
        onClick={(e) => {
          e.stopPropagation();
          onToggleVisible();
        }}
        className="grid h-4.5 w-4.5 shrink-0 place-items-center rounded-sm text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
      >
        {eyeHidden ? <EyeOff size={14} strokeWidth={1.8} /> : <Eye size={14} strokeWidth={1.8} />}
      </button>
    </div>
  );
}
