/**
 * PartsList — the Model tab's Parts rows (formerly the inline "Model Tree").
 * Clicking a row toggles its selection (accent bar + tinted row); clicking the
 * already-selected row clears the selection. The trailing material swatch opens
 * a picker to assign a library material to that part; the eye button toggles its
 * 3D visibility. Both trailing buttons stop propagation so they don't also
 * select. Hidden rows dim and show EyeOff. The "no model yet" case is handled
 * upstream in Inspector; this component only renders given an `objects` array.
 */
import { useState } from "react";
import { Eye, EyeOff, Trash2 } from "lucide-react";
import type { ModelObject } from "../../lib/artifacts";
import { engineRemoveImport } from "../../lib/ipc/engine";
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

export default function PartsList({
  objects,
  selectedId,
  hiddenIds,
  onSelect,
  onToggleVisible,
  materialOverrides = {},
  onSetPartMaterial = () => {},
}: {
  objects: ModelObject[];
  selectedId: string | null;
  hiddenIds: ReadonlySet<string>;
  onSelect: (id: string | null) => void;
  onToggleVisible: (id: string) => void;
  materialOverrides?: Record<string, import("../../lib/materials").Material>;
  onSetPartMaterial?: (
    partId: string,
    material: import("../../lib/materials").Material | null,
  ) => void;
}) {
  const [picker, setPicker] = useState<{ id: string; anchor: DOMRect } | null>(null);

  if (objects.length === 0) {
    return <div className="px-3.5 pb-2.5 pt-0.5 text-xs text-ink-3">Empty model</div>;
  }

  const openObject = picker ? (objects.find((o) => o.id === picker.id) ?? null) : null;

  return (
    <div className="pb-1">
      {objects.map((obj) => {
        const selected = obj.id === selectedId;
        const hidden = hiddenIds.has(obj.id);
        const isRef = obj.role === "reference";
        // Tint the swatch from the part's resolved base color (linear RGB). An
        // optimistic override wins; otherwise fall back to the resolved appearance,
        // then a neutral grey when an older artifact has no appearance.
        const overridden = materialOverrides[obj.id];
        const swatchHex = overridden
          ? overridden.colorHex
          : obj.appearance
            ? linearRgbToHex(obj.appearance.baseColor)
            : "#9aa0aa";
        return (
          <div
            key={obj.id}
            role="button"
            tabIndex={0}
            aria-pressed={selected}
            onClick={() => onSelect(selected ? null : obj.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(selected ? null : obj.id);
              }
            }}
            className={
              selected
                ? "flex cursor-pointer items-center gap-2.25 bg-accent-tint px-3.5 py-1.75 text-body shadow-[inset_2px_0_0_var(--color-accent)]"
                : "flex cursor-pointer items-center gap-2.25 px-3.5 py-1.75 text-body hover:bg-surface-2"
            }
          >
            <span
              className={
                selected
                  ? "h-3.75 w-3.75 shrink-0 rounded-sm border-[1.5px] border-accent bg-accent-tint"
                  : `h-3.75 w-3.75 shrink-0 rounded-sm border-[1.5px] ${
                      hidden ? "border-line-2" : "border-ink-3"
                    }`
              }
            />
            <span className={`truncate ${hidden ? "text-ink-3" : ""}`}>{obj.name}</span>
            {isRef ? (
              <span
                title="Imported reference (fit around it; not exported)"
                className="ml-auto shrink-0 rounded-md bg-accent-tint px-1.5 py-0.5 text-micro font-semibold text-accent"
              >
                Reference
              </span>
            ) : (
              <span className="ml-auto shrink-0 font-mono text-caption text-ink-3">
                {obj.kind || "Part"}
              </span>
            )}
            {/* References have no assignable material; show a remove action instead. */}
            {isRef ? (
              <button
                type="button"
                title="Remove reference"
                aria-label={`Remove ${obj.name}`}
                onClick={(e) => {
                  e.stopPropagation();
                  void engineRemoveImport(obj.id);
                }}
                className="grid h-4.5 w-4.5 shrink-0 place-items-center rounded-sm text-ink-3 transition-colors hover:bg-surface-2 hover:text-danger"
              >
                <Trash2 size={13} strokeWidth={1.8} />
              </button>
            ) : (
              <button
                type="button"
                title="Assign material"
                aria-label={`Material for ${obj.name}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setPicker({ id: obj.id, anchor: e.currentTarget.getBoundingClientRect() });
                }}
                className={`grid h-4.5 w-4.5 shrink-0 place-items-center rounded-sm transition-colors hover:bg-surface-2 ${
                  hidden ? "opacity-55" : ""
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
            )}
            <button
              type="button"
              title={hidden ? "Show part" : "Hide part"}
              aria-label={hidden ? `Show ${obj.name}` : `Hide ${obj.name}`}
              onClick={(e) => {
                e.stopPropagation();
                onToggleVisible(obj.id);
              }}
              className="grid h-4.5 w-4.5 shrink-0 place-items-center rounded-sm text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
            >
              {hidden ? (
                <EyeOff size={14} strokeWidth={1.8} />
              ) : (
                <Eye size={14} strokeWidth={1.8} />
              )}
            </button>
          </div>
        );
      })}

      {picker && openObject && (
        <PartMaterialPicker
          anchor={picker.anchor}
          currentMaterialId={
            materialOverrides[openObject.id]?.id ?? openObject.appearance?.material
          }
          onPick={(material) => {
            onSetPartMaterial(openObject.id, material);
            setPicker(null);
          }}
          onClearToDefault={() => {
            onSetPartMaterial(openObject.id, null);
            setPicker(null);
          }}
          onClose={() => setPicker(null)}
        />
      )}
    </div>
  );
}
