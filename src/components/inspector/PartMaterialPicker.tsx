/**
 * PartMaterialPicker — a frosted popover that assigns one of the workspace's
 * library materials to a single part (or clears the override back to the model's
 * own material).
 *
 * PURE PRESENTATIONAL: the part id lives in the parent (PartsList); this panel
 * only reports the chosen material id (or "clear") via callbacks. It loads the
 * available materials itself = global library + workspace library merged by id
 * (workspace wins), and renders each as a row with a shade ball (the same cached
 * WebGPU thumbnail the material cards use, with the tinted CSS-sphere fallback
 * while it renders) + label + `BASE · Finish` caption. A check marks the row
 * matching the part's current material.
 *
 * Visual language: the frosted `MENU_PANEL` recipe (src/lib/styles.ts), the
 * shade-ball look shared with the Materials cards, and the anchoring +
 * dismissal pattern from ViewportContextMenu (useDismiss + clamp-to-viewport).
 * The panel is `fixed`, anchored against the swatch button's viewport rect and
 * clamped so it never spills past an edge. No em dashes in user copy.
 */
import { useLayoutEffect, useState } from "react";
import { Check } from "lucide-react";

import { MENU_PANEL } from "../../lib/styles";
import { useDismiss } from "../../hooks/useDismiss";
import { useShadeBall } from "../../hooks/useShadeBall";
import { getGlobalMaterials, getWorkspaceMaterials, type Material } from "../../lib/materials";
import { MAT_COPY } from "../materials/copy";

export interface PartMaterialPickerProps {
  /** Anchor rect (the row swatch button) to position the popover against. */
  anchor: DOMRect;
  /** Current material id assigned to the part, if any (for a check mark). */
  currentMaterialId?: string;
  onPick: (material: Material) => void;
  onClearToDefault: () => void;
  onClose: () => void;
}

/** Fixed panel width; used for edge-clamp math. */
const PANEL_W = 256;
/** Keep the panel this far from the viewport edges when clamping. */
const EDGE_PAD = 8;
/** Gap between the anchor button and the panel's left edge. */
const ANCHOR_GAP = 6;

/** Title-case a single word ("matte" -> "Matte"). */
function cap(s: string): string {
  return s.length ? s[0].toUpperCase() + s.slice(1) : s;
}

/** Merge global + workspace libraries by id; workspace entries win. */
function mergeById(global: Material[], workspace: Material[]): Material[] {
  const byId = new Map<string, Material>();
  for (const m of global) byId.set(m.id, m);
  for (const m of workspace) byId.set(m.id, m);
  return [...byId.values()];
}

export default function PartMaterialPicker({
  anchor,
  currentMaterialId,
  onPick,
  onClearToDefault,
  onClose,
}: PartMaterialPickerProps) {
  const ref = useDismiss<HTMLDivElement>(true, onClose);

  const [materials, setMaterials] = useState<Material[] | null>(null);
  useLayoutEffect(() => {
    let live = true;
    Promise.all([getGlobalMaterials(), getWorkspaceMaterials()])
      .then(([g, w]) => {
        if (live) setMaterials(mergeById(g.materials, w.materials));
      })
      .catch(() => {
        if (live) setMaterials([]);
      });
    return () => {
      live = false;
    };
  }, []);

  // Edge-aware placement: prefer to sit just left of the swatch (it lives at the
  // row's right edge), flipping right if there is no room. Top-align to the
  // anchor, then clamp the whole panel inside the viewport using its measured
  // height. `fixed`, so we clamp against the window.
  const [pos, setPos] = useState<{ left: number; top: number }>({
    left: anchor.left,
    top: anchor.bottom,
  });
  useLayoutEffect(() => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const h = ref.current?.offsetHeight ?? 0;

    const leftAnchored = anchor.left - ANCHOR_GAP - PANEL_W;
    const left = leftAnchored >= EDGE_PAD ? leftAnchored : anchor.right + ANCHOR_GAP;
    const clampedLeft = Math.max(
      EDGE_PAD,
      Math.min(left, Math.max(EDGE_PAD, vw - PANEL_W - EDGE_PAD)),
    );

    const wantTop = anchor.top;
    const top = wantTop + h + EDGE_PAD > vh ? anchor.bottom - h : wantTop;
    const clampedTop = Math.max(EDGE_PAD, Math.min(top, Math.max(EDGE_PAD, vh - h - EDGE_PAD)));

    setPos({ left: clampedLeft, top: clampedTop });
  }, [anchor, materials, ref]);

  // The part is on its model default when it has no override, or when its
  // resolved material id is not one of the listed library entries (a built-in
  // like "pla"/"aluminum" that has no library card). That keeps a check visible:
  // an assigned library material checks its own row; anything else checks "Use
  // model default". While the list is still loading, leave it unchecked.
  const usingDefault =
    !currentMaterialId ||
    (materials !== null && !materials.some((m) => m.id === currentMaterialId));

  return (
    <div
      ref={ref}
      role="menu"
      aria-label={MAT_COPY.pickerHeading}
      style={{ position: "fixed", left: pos.left, top: pos.top, width: PANEL_W }}
      className={`${MENU_PANEL} max-h-[min(60vh,420px)] overflow-y-auto`}
    >
      <button
        type="button"
        role="menuitemradio"
        aria-checked={usingDefault}
        onClick={onClearToDefault}
        className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-body text-ink-2 transition-colors duration-100 hover:bg-surface-2 hover:text-ink"
      >
        <span className="grid h-6 w-6 flex-none place-items-center rounded-full border border-dashed border-line-3 text-ink-3">
          <span className="h-1.5 w-1.5 rounded-full bg-ink-3" />
        </span>
        <span className="flex-1 truncate">{MAT_COPY.useModelDefault}</span>
        {usingDefault && <Check size={14} strokeWidth={2.25} className="flex-none text-accent" />}
      </button>

      <div className="mx-1 my-1 h-px bg-line" />

      {materials === null ? (
        <div className="px-2 py-2 text-caption text-ink-3">{MAT_COPY.loading}</div>
      ) : materials.length === 0 ? (
        <div className="px-2 py-2 text-caption text-ink-3">{MAT_COPY.emptyGlobal}</div>
      ) : (
        materials.map((m) => (
          <MaterialRow
            key={m.id}
            material={m}
            checked={m.id === currentMaterialId}
            onClick={() => onPick(m)}
          />
        ))
      )}
    </div>
  );
}

/** One material row: shade ball + label + `BASE · Finish` caption + check. */
function MaterialRow({
  material,
  checked,
  onClick,
}: {
  material: Material;
  checked: boolean;
  onClick: () => void;
}) {
  const thumb = useShadeBall(material);
  const meta = `${material.base.toUpperCase()} · ${cap(material.finish)}`;

  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={checked}
      onClick={onClick}
      title={material.label}
      className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors duration-100 hover:bg-surface-2"
    >
      {thumb ? (
        <img src={thumb} alt="" draggable={false} className="h-6 w-6 flex-none select-none" />
      ) : (
        <MiniShadeBall colorHex={material.colorHex} />
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-body text-ink">{material.label}</span>
        <span className="block truncate font-mono text-micro tracking-[0.01em] text-ink-3">
          {meta}
        </span>
      </span>
      {checked && <Check size={14} strokeWidth={2.25} className="flex-none text-accent" />}
    </button>
  );
}

/**
 * The tinted CSS-sphere fallback shown while the WebGPU thumbnail renders. Same
 * fake-PBR recipe the material cards use, sized down for the row.
 */
function MiniShadeBall({ colorHex }: { colorHex: string }) {
  return (
    <span
      aria-hidden
      className="relative h-6 w-6 flex-none rounded-full shadow-[inset_0_-3px_5px_rgba(8,10,18,.3),inset_0_2px_3px_rgba(255,255,255,.16)]"
      style={{
        ["--albedo" as string]: colorHex,
        background:
          "radial-gradient(circle at 35% 29%, color-mix(in srgb, var(--albedo), white 78%) 0%, transparent 44%)," +
          "radial-gradient(circle at 66% 76%, rgba(150,175,255,.4) 0%, transparent 40%)," +
          "radial-gradient(125% 125% at 47% 35%, color-mix(in srgb, var(--albedo), white 14%), color-mix(in srgb, var(--albedo), black 40%) 84%)",
      }}
    />
  );
}
