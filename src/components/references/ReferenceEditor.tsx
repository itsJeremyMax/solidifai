/**
 * ReferenceEditor — add / edit a reference entry, as a nested route
 * (`references/new`, `references/:entryId`) rendered over the list. A centered
 * modal (backdrop + Escape close via useDismiss). Saves persist a single entry
 * back through the list's Outlet context; editing a builtin entry creates a user
 * copy that shadows it.
 */
import { useEffect, useMemo, useState } from "react";
import { BookMarked, Plus, X } from "lucide-react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";

import type { ReferenceEntry } from "../../lib/ipc/references";
import { useDismiss } from "../../hooks/useDismiss";
import { useGoBack } from "../../hooks/useGoBack";
import { ACCENT_CTA } from "../../lib/styles";
import type { ReferencesOutletContext } from "./referencesContext";

const ICON_STROKE = 1.7;

/** One editable dims row: a string key and the raw text the value parses from. */
interface DimRow {
  key: string;
  /** Raw text; parsed to a number or number[] on save. */
  raw: string;
}

/** Serialize a stored dim value back to the raw text shown in its input. */
function valueToRaw(v: number | number[]): string {
  return Array.isArray(v) ? `[${v.join(", ")}]` : String(v);
}

/** Parse one raw dim value to a number or number[]; throws on anything else. */
function parseDimValue(raw: string): number | number[] {
  const parsed = JSON.parse(raw) as unknown;
  if (typeof parsed === "number" && Number.isFinite(parsed)) return parsed;
  if (Array.isArray(parsed) && parsed.every((n) => typeof n === "number" && Number.isFinite(n))) {
    return parsed as number[];
  }
  throw new Error("must be a number or a list of numbers, e.g. 18 or [85, 56]");
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-1.5 block text-micro font-bold uppercase tracking-eyebrow text-ink-3">
      {children}
    </span>
  );
}

const INPUT_BASE =
  "h-9.5 w-full rounded-lg border border-line-2 bg-surface-2 px-3 text-sm text-ink outline-none transition-colors duration-150 placeholder:text-ink-3 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint";

export default function ReferenceEditor() {
  const navigate = useNavigate();
  const { entryId: rawId } = useParams();
  const entryId = rawId ? decodeURIComponent(rawId) : undefined;
  const ctx = useOutletContext<ReferencesOutletContext>();

  const isNew = entryId === undefined;
  const existing = isNew ? null : (ctx.entries.find((e) => e.id === entryId) ?? null);
  const editingBuiltin = existing?.builtin ?? false;
  const close = useGoBack("..", { replace: true });
  const ref = useDismiss<HTMLDivElement>(true, close);

  // Stale deep link: editing an id that no longer exists.
  useEffect(() => {
    if (!isNew && !existing) navigate("..", { replace: true });
  }, [isNew, existing, navigate]);

  const [id, setId] = useState(existing?.id ?? "");
  const [category, setCategory] = useState(existing?.category ?? "");
  const [aliases, setAliases] = useState((existing?.aliases ?? []).join(", "));
  const [source, setSource] = useState(existing?.source ?? "");
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [dims, setDims] = useState<DimRow[]>(() => {
    const rows = Object.entries(existing?.dims_mm ?? {}).map(([key, v]) => ({
      key,
      raw: valueToRaw(v),
    }));
    return rows.length > 0 ? rows : [{ key: "", raw: "" }];
  });
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // The id is locked when editing an existing entry (it's the identity).
  const idLocked = !isNew;
  const trimmedId = id.trim();
  const idTaken =
    isNew &&
    ctx.entries.some((e) => !e.builtin && e.id.trim().toLowerCase() === trimmedId.toLowerCase());

  // Per-row inline dim error (key index -> message), computed only on submit.
  const [dimErrors, setDimErrors] = useState<Record<number, string>>({});

  const canSave = useMemo(
    () =>
      trimmedId.length > 0 &&
      category.trim().length > 0 &&
      /^https?:\/\/.+/.test(source.trim()) &&
      !idTaken &&
      !saving,
    [trimmedId, category, source, idTaken, saving],
  );

  const updateDim = (i: number, patch: Partial<DimRow>) => {
    setDims((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  };
  const addDim = () => setDims((rows) => [...rows, { key: "", raw: "" }]);
  const removeDim = (i: number) => setDims((rows) => rows.filter((_, idx) => idx !== i));

  const submit = async () => {
    if (!canSave) return;

    // Parse the dims rows, collecting per-row errors. Empty rows are dropped.
    const dims_mm: Record<string, number | number[]> = {};
    const errs: Record<number, string> = {};
    dims.forEach((row, i) => {
      const key = row.key.trim();
      const raw = row.raw.trim();
      if (!key && !raw) return; // blank row, ignore
      if (!key) {
        errs[i] = "give this value a name";
        return;
      }
      if (!raw) {
        errs[i] = "give this value a number";
        return;
      }
      try {
        dims_mm[key] = parseDimValue(raw);
      } catch (e) {
        errs[i] = e instanceof Error ? e.message : "invalid value";
      }
    });
    if (Object.keys(errs).length > 0) {
      setDimErrors(errs);
      return;
    }
    setDimErrors({});

    const aliasList = aliases
      .split(",")
      .map((a) => a.trim())
      .filter(Boolean);

    const entry: ReferenceEntry = {
      // Editing a builtin keeps its id so the saved user copy shadows it.
      id: idLocked ? existing!.id : trimmedId,
      category: category.trim(),
      dims_mm,
      source: source.trim(),
      ...(aliasList.length > 0 ? { aliases: aliasList } : {}),
      ...(existing?.mounting_holes ? { mounting_holes: existing.mounting_holes } : {}),
      ...(notes.trim() ? { notes: notes.trim() } : {}),
      // Keep the verification lineage on edits; the host re-stamps origin.
      ...(existing?.verified_at ? { verified_at: existing.verified_at } : {}),
      ...(existing?.verified_in ? { verified_in: existing.verified_in } : {}),
    };

    setSaving(true);
    setSaveError(null);
    try {
      await ctx.save(entry);
      close();
    } catch (e) {
      setSaveError(String(e));
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-[rgba(18,20,28,.34)] px-5 py-8 backdrop-blur-xs">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="reference-editor-title"
        className="animate-rise flex max-h-full w-full max-w-130 flex-col rounded-panel border border-line-2 bg-surface shadow-float"
      >
        <div className="flex items-center gap-2.5 px-5 pt-5">
          <span className="grid h-8.5 w-8.5 shrink-0 place-items-center rounded-xl border border-line-2 bg-surface-2 text-accent">
            <BookMarked size={17} strokeWidth={ICON_STROKE} />
          </span>
          <h2 id="reference-editor-title" className="text-base font-bold tracking-snug text-ink">
            {isNew ? "Add reference" : editingBuiltin ? "Edit builtin reference" : "Edit reference"}
          </h2>
          <div className="flex-1" />
          <button
            type="button"
            onClick={close}
            aria-label="Close"
            className="grid h-7 w-7 place-items-center rounded-lg text-ink-3 transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
          >
            <X size={16} strokeWidth={ICON_STROKE} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {editingBuiltin && (
            <p className="mb-4 rounded-[11px] border border-accent-line bg-accent-tint px-3.25 py-2.5 text-caption leading-relaxed text-ink-2">
              Saving creates your own copy that overrides the builtin entry.
            </p>
          )}

          <label className="mb-3.5 block">
            <FieldLabel>Id</FieldLabel>
            <input
              type="text"
              value={id}
              autoFocus={isNew}
              disabled={idLocked}
              spellCheck={false}
              placeholder="raspberry-pi-5"
              aria-invalid={idTaken}
              onChange={(e) => setId(e.target.value)}
              className={`${INPUT_BASE} font-mono disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-ink-3 ${
                idTaken ? "border-danger-line focus:border-danger focus:ring-danger-bg" : ""
              }`}
            />
            {idTaken && (
              <span className="mt-1.5 block text-caption text-danger">
                A reference with that id already exists.
              </span>
            )}
          </label>

          <label className="mb-3.5 block">
            <FieldLabel>Category</FieldLabel>
            <input
              type="text"
              value={category}
              spellCheck={false}
              placeholder="sbc"
              onChange={(e) => setCategory(e.target.value)}
              className={INPUT_BASE}
            />
          </label>

          <div className="mb-3.5">
            <FieldLabel>Dimensions (mm)</FieldLabel>
            <div className="flex flex-col gap-2">
              {dims.map((row, i) => (
                <div key={i}>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={row.key}
                      spellCheck={false}
                      placeholder="pcb"
                      aria-label={`Dimension ${i + 1} name`}
                      onChange={(e) => updateDim(i, { key: e.target.value })}
                      className={`${INPUT_BASE} font-mono`}
                    />
                    <input
                      type="text"
                      value={row.raw}
                      spellCheck={false}
                      placeholder="[85, 56, 1.4]"
                      aria-label={`Dimension ${i + 1} value`}
                      onChange={(e) => updateDim(i, { raw: e.target.value })}
                      className={`${INPUT_BASE} font-mono`}
                    />
                    <button
                      type="button"
                      aria-label={`Remove dimension ${i + 1}`}
                      onClick={() => removeDim(i)}
                      className="grid h-9.5 w-9 shrink-0 place-items-center rounded-lg text-ink-3 transition-colors duration-150 hover:bg-danger-bg hover:text-danger"
                    >
                      <X size={15} strokeWidth={ICON_STROKE} />
                    </button>
                  </div>
                  {dimErrors[i] && (
                    <span className="mt-1 block text-caption text-danger">{dimErrors[i]}</span>
                  )}
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={addDim}
              className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-lg border border-line-2 bg-surface px-2.75 text-caption font-medium text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink"
            >
              <Plus size={14} strokeWidth={2} />
              Add dimension
            </button>
          </div>

          <label className="mb-3.5 block">
            <FieldLabel>Aliases</FieldLabel>
            <input
              type="text"
              value={aliases}
              spellCheck={false}
              placeholder="rpi5, pi 5 (comma separated)"
              onChange={(e) => setAliases(e.target.value)}
              className={INPUT_BASE}
            />
          </label>

          <label className="mb-3.5 block">
            <FieldLabel>Source</FieldLabel>
            <input
              type="text"
              value={source}
              spellCheck={false}
              placeholder="https://datasheets.example.com/part"
              onChange={(e) => setSource(e.target.value)}
              className={INPUT_BASE}
            />
          </label>

          <label className="block">
            <FieldLabel>Notes</FieldLabel>
            <textarea
              value={notes}
              spellCheck={false}
              rows={3}
              placeholder="Anything worth remembering about this part."
              onChange={(e) => setNotes(e.target.value)}
              className="w-full resize-y rounded-lg border border-line-2 bg-surface-2 px-3 py-2 text-sm leading-relaxed text-ink outline-none transition-colors duration-150 placeholder:text-ink-3 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint"
            />
          </label>
        </div>

        <div className="flex items-center justify-end gap-2.25 border-t border-line-2 px-5 py-3.5">
          {saveError && (
            <span
              className="mr-auto max-w-60 truncate font-mono text-caption text-danger"
              title={saveError}
            >
              {saveError}
            </span>
          )}
          <button
            type="button"
            onClick={close}
            className="inline-flex h-9 items-center rounded-lg px-3.5 text-body font-medium text-ink-2 transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!canSave}
            className={`${ACCENT_CTA} h-9 px-4 disabled:opacity-45 disabled:hover:bg-accent`}
          >
            {isNew ? "Add reference" : editingBuiltin ? "Save my copy" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
