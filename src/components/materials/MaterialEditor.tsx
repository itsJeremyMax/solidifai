/**
 * MaterialEditor — the right-side editor drawer.
 *
 * Edits a single material draft: name, base substance, color, and finish. There
 * are no raw PBR sliders; the finish presets do the work, and the manufacturing
 * PROCESS is *derived* from the base substance and shown as a read-only
 * inferred callout. The live shade ball lives in a floating
 * MaterialPreviewCard to the LEFT of this drawer (rendered by MaterialsView), so
 * the form stays short while the preview tracks every edit.
 *
 * All visible strings come from MAT_COPY (no em dashes, hand-written voice).
 * The component is presentational + locally-stateless: every edit is reported up
 * through `onChange`, and the parent owns the draft + persistence.
 */
import { Check, ChevronDown, Pin, Trash2, X } from "lucide-react";
import type { Material } from "../../lib/materials";
import { CATALOG, processForBase } from "../../lib/materials";
import { ACCENT_CTA } from "../../lib/styles";
import { MAT_COPY } from "./copy";

const ICON_STROKE = 1.7;

const BASES = Object.entries(CATALOG.bases).map(([id, entry]) => ({ id, label: entry.label }));
const DENSITY = Object.fromEntries(
  Object.entries(CATALOG.bases).map(([id, entry]) => [id, entry.density]),
);

const FINISHES: Material["finish"][] = ["matte", "satin", "gloss", "metallic"];
const PALETTE = [
  "#bcbfc4",
  "#1f222a",
  "#2b6cff",
  "#19a957",
  "#ff6a23",
  "#e0a23b",
  "#d23b3b",
  "#dfe7e6",
];

/** Lowercase, hyphenated slug of a label, for the canonical id. */
// Shared with MaterialsView (the editor's sibling); only costs this file's fast refresh.
// eslint-disable-next-line react-refresh/only-export-components
export function slugify(label: string): string {
  return (
    label
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "material"
  );
}

function cap(s: string): string {
  return s.length ? s[0].toUpperCase() + s.slice(1) : s;
}

interface MaterialEditorProps {
  /** The material being edited, or a fresh draft for "New material". */
  draft: Material;
  /** True when this is a never-saved draft (id derives from the name live). */
  isNew: boolean;
  /** Which library this drawer edits; gates the workspace-only Pin affordance. */
  scope: "global" | "workspace";
  /**
   * True when the draft is a global-origin material not yet in the workspace.
   * The footer then offers a single "Pin to workspace" action instead of the
   * Save / Set default / Delete controls. Only ever true in workspace scope.
   */
  pinning?: boolean;
  isDefault: boolean;
  onChange: (next: Material) => void;
  onSave: () => void;
  onSetDefault: () => void;
  /** Copies the draft into the active workspace (used when `pinning`). */
  onPin?: () => void;
  onDelete: () => void;
  onClose: () => void;
  /** When set, Delete is disabled and shows this as a tooltip. */
  deleteBlockedReason?: string;
}

export default function MaterialEditor({
  draft,
  isNew,
  scope,
  pinning = false,
  isDefault,
  onChange,
  onSave,
  onSetDefault,
  onPin,
  onDelete,
  onClose,
  deleteBlockedReason,
}: MaterialEditorProps) {
  const process = processForBase(draft.base);
  const processLabel = process
    ? (MAT_COPY.processLabel[process] ?? process.toUpperCase())
    : "Unknown process";
  const density = DENSITY[draft.base];

  // The canonical id: locked to the saved id once it exists; live-derived from
  // the name while the material is brand new.
  const canonicalId = isNew ? slugify(draft.label) : draft.id;

  // Color is valid when it is a #rrggbb hex; an invalid in-progress value still
  // lets the user keep typing but won't recolor the preview to garbage.
  const hex = draft.colorHex;
  const hexValid = /^#[0-9a-fA-F]{6}$/.test(hex);
  const canSave = draft.label.trim().length > 0 && hexValid;

  // Pin is only ever offered in workspace scope for a global-origin material that
  // is not yet pinned. In global scope there is no unambiguous target workspace,
  // so we never enter pin mode there.
  const pinMode = pinning && scope === "workspace" && onPin != null;

  const update = (patch: Partial<Material>) => onChange({ ...draft, ...patch });

  const setHex = (raw: string) => {
    let v = raw.trim();
    if (v && !v.startsWith("#")) v = `#${v}`;
    update({ colorHex: v.toUpperCase() });
  };

  return (
    <div className="absolute inset-0 z-20 flex justify-end" role="dialog" aria-modal="true">
      <button
        type="button"
        aria-label={MAT_COPY.close}
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-[rgba(20,23,30,.18)] backdrop-blur-[.5px]"
      />

      <aside className="animate-rise relative flex h-full w-[354px] flex-col border-l border-line-2 bg-surface shadow-[-18px_0_48px_-28px_rgba(16,18,24,.35)]">
        {/* head */}
        <div className="flex items-center gap-2.5 border-b border-line px-4 pb-3.25 pt-3.75">
          <div className="min-w-0">
            <div className="text-sm font-semibold tracking-[-0.01em] text-ink">
              {pinMode ? MAT_COPY.pinTitle : isNew ? MAT_COPY.newTitle : MAT_COPY.editTitle}
            </div>
            {!isNew && (
              <div className="truncate text-caption text-ink-3">
                {pinMode ? MAT_COPY.pinSubtitle : draft.label}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={MAT_COPY.close}
            className="ml-auto grid h-7 w-7 place-items-center rounded-md border border-transparent text-ink-3 transition-colors duration-150 hover:border-line-2 hover:bg-surface-2"
          >
            <X size={16} strokeWidth={1.8} />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-4.5 overflow-y-auto px-4.5 py-5">
          {/* name */}
          <Field label={MAT_COPY.fieldName}>
            <input
              value={draft.label}
              placeholder={MAT_COPY.namePlaceholder}
              onChange={(e) => update({ label: e.target.value })}
              className="h-8.5 w-full rounded-lg border border-line-2 bg-surface-2 px-2.75 text-body text-ink outline-none transition-colors duration-150 placeholder:text-ink-3 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint"
            />
          </Field>
          <Field label={MAT_COPY.fieldBase} hint={MAT_COPY.baseHint}>
            <div className="relative">
              <select
                value={draft.base}
                onChange={(e) => update({ base: e.target.value })}
                className="h-8.5 w-full cursor-pointer appearance-none rounded-lg border border-line-2 bg-surface-2 pl-2.75 pr-9 text-body text-ink outline-none transition-colors duration-150 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint"
              >
                {BASES.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.label}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={15}
                strokeWidth={1.8}
                className="pointer-events-none absolute right-2.75 top-1/2 -translate-y-1/2 text-ink-3"
              />
            </div>
          </Field>

          {/* color */}
          <Field label={MAT_COPY.fieldColor}>
            <div className="flex items-center gap-2.5">
              <label
                className="h-8.5 w-8.5 flex-none cursor-pointer rounded-lg border border-[rgba(0,0,0,.12)] shadow-[inset_0_1px_2px_rgba(255,255,255,.4),inset_0_-3px_6px_rgba(0,0,0,.12)]"
                style={{ background: hexValid ? hex : "#bcbfc4" }}
              >
                <input
                  type="color"
                  value={hexValid ? hex : "#bcbfc4"}
                  onChange={(e) => setHex(e.target.value)}
                  className="sr-only"
                  aria-label={MAT_COPY.fieldColor}
                />
              </label>
              <input
                value={hex}
                onChange={(e) => setHex(e.target.value)}
                spellCheck={false}
                maxLength={7}
                className="h-8.5 flex-1 rounded-lg border border-line-2 bg-surface-2 px-2.75 font-mono text-body uppercase text-ink outline-none transition-colors duration-150 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint"
              />
            </div>
            <div className="mt-0.5 flex gap-1.5">
              {PALETTE.map((c) => {
                const on = hex.toLowerCase() === c.toLowerCase();
                return (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setHex(c)}
                    aria-label={c}
                    aria-pressed={on}
                    className={`h-4.5 w-4.5 rounded-[5px] border border-[rgba(0,0,0,.1)] transition-transform duration-100 ease-out-soft hover:scale-110 ${
                      on
                        ? "shadow-[0_0_0_2px_var(--color-surface),0_0_0_3.5px_var(--color-accent)]"
                        : ""
                    }`}
                    style={{ background: c }}
                  />
                );
              })}
            </div>
          </Field>
          <Field label={MAT_COPY.fieldFinish}>
            <div className="flex gap-0.5 rounded-[10px] border border-line-2 bg-surface-2 p-0.75">
              {FINISHES.map((f) => {
                const on = draft.finish === f;
                return (
                  <button
                    key={f}
                    type="button"
                    onClick={() => update({ finish: f })}
                    aria-pressed={on}
                    className={`flex-1 rounded-[7px] px-1 py-1.75 text-caption transition duration-150 ease-out-soft ${
                      on
                        ? "bg-surface font-semibold text-ink shadow-[0_1px_2px_rgba(16,18,24,.1)]"
                        : "font-medium text-ink-2 hover:text-ink"
                    }`}
                  >
                    {cap(f)}
                  </button>
                );
              })}
            </div>
          </Field>

          {/* inferred process callout */}
          <div className="flex flex-col gap-1.75 rounded-[11px] border border-accent-line bg-[linear-gradient(180deg,var(--color-accent-tint),rgba(43,108,255,.04))] px-3.25 py-3">
            <div className="flex items-center gap-2.25">
              <span className="grid h-6.5 w-6.5 flex-none place-items-center rounded-lg border border-accent-line bg-surface text-accent">
                <ProcessGlyph />
              </span>
              <span className="text-body font-semibold text-ink">{processLabel}</span>
              <span className="ml-auto rounded-full border border-accent-line bg-surface px-2 py-0.5 font-mono text-micro text-accent">
                {MAT_COPY.processInferred}
              </span>
            </div>
            <div className="text-micro leading-normal text-ink-2">{MAT_COPY.processNote}</div>
          </div>
          <div className="flex items-center justify-between border-t border-dashed border-line-2 pt-3 text-caption text-ink-3">
            <span>
              {MAT_COPY.densityLabel}{" "}
              <b className="font-mono font-medium text-ink-2">
                {density != null ? `${density.toFixed(2)} g/cm³` : "n/a"}
              </b>
            </span>
            <span>
              {MAT_COPY.canonicalLabel}{" "}
              <b className="font-mono font-medium text-ink-2">{canonicalId}</b>
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2.25 border-t border-line bg-surface-2 px-4 py-3.25">
          {pinMode ? (
            <button
              type="button"
              onClick={onPin}
              disabled={!canSave}
              className={`${ACCENT_CTA} h-8.5 flex-1 justify-center disabled:opacity-45 disabled:hover:bg-accent`}
            >
              <Pin size={15} strokeWidth={ICON_STROKE} />
              {MAT_COPY.pin}
            </button>
          ) : isDefault ? (
            <button
              type="button"
              onClick={onSave}
              disabled={!canSave}
              className={`${ACCENT_CTA} h-8.5 flex-1 justify-center disabled:opacity-45 disabled:hover:bg-accent`}
            >
              <Check size={15} strokeWidth={ICON_STROKE} />
              {MAT_COPY.save}
            </button>
          ) : (
            // Not the default: the primary CTA saves and promotes to default; a quiet "Save only" sits beside it.
            <>
              <button
                type="button"
                onClick={() => {
                  onSave();
                  onSetDefault();
                }}
                disabled={!canSave}
                className={`${ACCENT_CTA} h-8.5 flex-1 justify-center disabled:opacity-45 disabled:hover:bg-accent`}
              >
                <Check size={15} strokeWidth={ICON_STROKE} />
                {MAT_COPY.setDefault}
              </button>
              <button
                type="button"
                onClick={onSave}
                disabled={!canSave}
                title={MAT_COPY.save}
                className="inline-flex h-8.5 items-center rounded-lg border border-line-2 bg-surface px-3 text-body font-medium text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink disabled:opacity-45 disabled:hover:border-line-2 disabled:hover:text-ink-2"
              >
                {MAT_COPY.save}
              </button>
            </>
          )}

          {/* Delete only applies to a material that lives in this library; a
              not-yet-pinned global material has nothing to delete here. */}
          {!pinMode && (
            <button
              type="button"
              onClick={onDelete}
              disabled={deleteBlockedReason != null}
              title={deleteBlockedReason ?? MAT_COPY.delete}
              aria-label={MAT_COPY.delete}
              className="grid h-8.5 w-8.5 place-items-center rounded-lg border border-line-2 bg-surface text-ink-2 transition-colors duration-150 hover:border-danger-line hover:bg-danger-bg hover:text-danger disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-line-2 disabled:hover:bg-surface disabled:hover:text-ink-2"
            >
              <Trash2 size={16} strokeWidth={ICON_STROKE} />
            </button>
          )}
        </div>
      </aside>
    </div>
  );
}

/** A labelled field column (label + optional muted hint, then the control). */
function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="flex items-center gap-1.5 text-caption font-semibold tracking-[-0.005em] text-ink-2">
        {label}
        {hint && <span className="font-normal text-ink-3">{hint}</span>}
      </span>
      {children}
    </div>
  );
}

/** The small "process" glyph used in the inferred-process callout. */
function ProcessGlyph() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={ICON_STROKE}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M22 12H2M5 12V7l4 2 3-5 3 5 4-2v5M5 12v5h14v-5" />
    </svg>
  );
}
