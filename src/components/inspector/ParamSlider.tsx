/**
 * ParamSlider — a functional slider bound to one model parameter.
 *
 * Holds an optimistic local value (`local`) that both the drag handler and the
 * click-to-edit readout write through, so the thumb, the readout, and the engine
 * commit always move together via the SAME `onCommit` path (debounced upstream
 * in {@link Inspector}).
 *
 * Reconcile: when a newer build arrives (`buildId` changes) `local` snaps to the
 * engine's authoritative `value` — UNLESS this field is actively being edited or
 * dragged, so a fresh `model-updated` never yanks the input out from under the
 * user. While typing, the pending build is remembered and applied the moment
 * editing ends. While dragging, intermediate builds (the engine echoing values
 * the user has already dragged past) are consumed WITHOUT snapping `local`, so
 * the thumb tracks the finger; only a build that lands after the drag ends — the
 * result of the final commit — reconciles the slider to the engine's truth.
 */
import { useEffect, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";

import type { NumericParamSchemaEntry } from "../../lib/artifacts";
import { round1 } from "../../lib/format";

/** Title-case a param key like `hole_dia` / `holeDia` → `Hole Dia`. */
function titleCase(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .trim()
    .split(/\s+/)
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

/** Fractional position [0..1] of `value` within `[min, max]`, clamped. */
function ratio(value: number, min: number, max: number): number {
  if (!(max > min)) return 0;
  return Math.min(1, Math.max(0, (value - min) / (max - min)));
}

/**
 * Clamp `value` to `[min, max]` and snap to the nearest `step` (anchored at
 * `min`). Mirrors what the native range input does, so typed values land on the
 * same grid as dragged ones. Returns `null` for non-finite input.
 */
function clampSnap(value: number, entry: NumericParamSchemaEntry): number | null {
  if (!Number.isFinite(value)) return null;
  const { min, max, step } = entry;
  let v = Math.min(max, Math.max(min, value));
  if (step > 0) {
    const snapped = min + Math.round((v - min) / step) * step;
    // Re-clamp: rounding can nudge past max (e.g. last step overshoots).
    v = Math.min(max, Math.max(min, snapped));
    // Kill floating-point fuzz introduced by the snap arithmetic.
    v = Math.round(v * 1e6) / 1e6;
  }
  return v;
}

interface ParamSliderProps {
  paramKey: string;
  entry: NumericParamSchemaEntry;
  /** Authoritative value from the latest model build (source of truth). */
  value: number;
  /** Monotonic build id — bumps when fresh artifacts arrive (reconcile trigger). */
  buildId: number;
  /** Commit a new value to the engine (already debounced upstream). */
  onCommit: (key: string, value: number) => void;
  /** True when THIS slider's value readout is in click-to-edit mode. */
  editing: boolean;
  /** Open this slider's value editor (closes any other open one upstream). */
  onEditOpen: (key: string) => void;
  /** Close the editor (whether committed or cancelled). */
  onEditClose: () => void;
}

export default function ParamSlider({
  paramKey,
  entry,
  value,
  buildId,
  onCommit,
  editing,
  onEditOpen,
  onEditClose,
}: ParamSliderProps) {
  // Optimistic local value — what the user sees while dragging, before the
  // engine has rebuilt and echoed the value back.
  const [local, setLocal] = useState<number>(value);
  // The build id we last reconciled against. When the incoming buildId advances,
  // the engine has spoken — adopt its value as truth.
  const reconciledBuild = useRef<number>(buildId);
  // True while the user is actively dragging the range thumb. Suspends reconcile
  // (like `editing`) so a mid-drag `model-updated` can't snap the thumb back to a
  // value the user already dragged past. Toggles only on pointer down/up (two
  // renders per drag), never per move.
  const [dragging, setDragging] = useState<boolean>(false);

  // Draft text while the readout is in edit mode (a real string so partial
  // input like "1." / "-" is allowed without fighting the user).
  const [draft, setDraft] = useState<string>("");
  const inputRef = useRef<HTMLInputElement | null>(null);
  // Set by Escape so the blur it triggers (input unmounts) doesn't also commit.
  const cancelledRef = useRef<boolean>(false);

  useEffect(() => {
    if (buildId === reconciledBuild.current) return;
    // Don't reconcile while the user is mid-edit — that would replace what
    // they're typing. The build id stays "unreconciled"; the effect re-runs and
    // adopts the value as soon as `editing` flips back to false.
    if (editing) return;
    // While dragging, consume the build (so we don't snap to it later) but keep
    // the user's `local` value — the engine is just echoing a value they've
    // already dragged past. The final commit's build lands after the drag ends
    // (higher buildId) and reconciles then.
    if (dragging) {
      reconciledBuild.current = buildId;
      return;
    }
    reconciledBuild.current = buildId;
    setLocal(value);
  }, [buildId, value, editing, dragging]);

  // Clear `dragging` when the pointer is released, even if that happens off the
  // thumb (range thumbs capture the pointer, so pointerup may not fire on the
  // input itself). The listener only exists for the duration of a drag.
  useEffect(() => {
    if (!dragging) return;
    const end = () => setDragging(false);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
    return () => {
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
    };
  }, [dragging]);

  // Entering edit mode: seed the draft from the live value AND its unit (e.g.
  // "20 mm") so the user edits the full string; focus + select.
  useEffect(() => {
    if (!editing) return;
    cancelledRef.current = false;
    setDraft(entry.unit ? `${round1(local)} ${entry.unit}` : round1(local));
    // Focus on the next frame so the input is mounted; select for quick replace.
    const id = requestAnimationFrame(() => {
      const el = inputRef.current;
      if (el) {
        el.focus();
        el.select();
      }
    });
    return () => cancelAnimationFrame(id);
    // Snapshot `local`/`entry.unit` only when the editor opens; depending on them
    // would re-seed mid-edit and clobber what the user is typing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = Number(e.target.value);
    setLocal(next);
    // During a pointer drag, defer the (expensive) engine commit to release;
    // keyboard arrow changes (no active drag) commit immediately as discrete steps.
    if (!dragging) onCommit(paramKey, next);
  };

  /**
   * Push a typed value through the SAME path the slider drag uses.
   *
   * The field now holds value + unit (e.g. "20 mm"), so we parse the LEADING
   * number with `parseFloat` — it reads `20` from `"20 mm"`, `"20mm"`, or a bare
   * `"20"` and ignores whatever trailing unit text was typed (all params are mm;
   * the unit is cosmetic). Empty / no-leading-number → `NaN` → revert (no commit).
   */
  const applyTyped = (raw: string): boolean => {
    const num = parseFloat(raw); // leading number; NaN if none
    const parsed = clampSnap(num, entry);
    if (parsed === null) return false; // NaN / Infinity → caller reverts
    setLocal(parsed); // same optimistic local state as the drag
    onCommit(paramKey, parsed); // same debounced engine commit as the drag
    return true;
  };

  /** Commit on Enter / blur — apply if valid, otherwise silently revert. */
  const commitEdit = () => {
    // Escape already closed us; the trailing blur must not re-apply the draft.
    if (cancelledRef.current) {
      cancelledRef.current = false;
      return;
    }
    applyTyped(draft); // invalid/empty just leaves `local` untouched (revert)
    onEditClose();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commitEdit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancelledRef.current = true; // suppress the commit on the ensuing blur
      onEditClose(); // cancel — no commit, `local` unchanged
    }
  };

  const pct = ratio(local, entry.min, entry.max) * 100;
  const defaultPct = ratio(entry.value, entry.min, entry.max) * 100;
  const modified = Math.abs(local - entry.value) > 1e-9;
  const resetToDefault = () => {
    setLocal(entry.value);
    onCommit(paramKey, entry.value);
  };
  const unit = entry.unit ? ` ${entry.unit}` : "";
  // Short subtitle under the name — only when the engine supplied a non-empty
  // description. Empty desc renders the row exactly as before (no layout shift).
  const hasDesc = entry.desc.trim().length > 0;
  // NOTE: assumes one Inspector panel is mounted at a time (single-panel app).
  // If multiple panels ever mount the same model, prefix this with a useId().
  const descId = `param-desc-${paramKey}`;

  return (
    <div className="group px-3.5 py-2.25">
      <div className="mb-2">
        <div className="flex items-baseline justify-between gap-2">
          <span className="min-w-0 truncate text-xs font-medium text-ink-2">
            {titleCase(paramKey)}
          </span>
          {modified && !editing && (
            <button
              type="button"
              onClick={resetToDefault}
              title={`Reset to ${round1(entry.value)}${unit}`}
              aria-label={`Reset ${titleCase(paramKey)} to default`}
              className="ml-auto grid h-4 w-4 shrink-0 place-items-center self-center rounded-sm text-ink-3 opacity-0 transition-opacity hover:bg-surface-2 hover:text-ink focus-visible:opacity-100 group-hover:opacity-100"
            >
              <RotateCcw size={11} strokeWidth={2} />
            </button>
          )}
          {editing ? (
            <input
              ref={inputRef}
              type="text"
              inputMode="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              onBlur={commitEdit}
              aria-label={`${titleCase(paramKey)} value`}
              className="w-20 rounded bg-transparent px-1 py-px text-right font-mono text-xs font-medium text-ink outline-none ring-1 ring-accent focus:ring-2 focus:ring-accent"
            />
          ) : (
            <button
              type="button"
              onClick={() => onEditOpen(paramKey)}
              title="Click to edit"
              aria-label={`Edit ${titleCase(paramKey)} value`}
              className="-mr-1 cursor-text rounded px-1 py-px font-mono text-xs font-medium text-ink ring-1 ring-transparent transition-colors hover:bg-surface-2 hover:ring-line-2"
            >
              {round1(local)}
              {unit}
            </button>
          )}
        </div>
        {hasDesc && (
          <p id={descId} className="mt-0.5 text-caption leading-snug text-ink-3">
            {entry.desc.trim()}
          </p>
        )}
      </div>
      <div className="group/track relative h-1 rounded-full bg-line-2">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-accent"
          style={{ width: `${pct}%` }}
        />
        {/* default-value notch — the "home" position the reset returns to */}
        {modified && (
          <div
            className="pointer-events-none absolute top-1/2 h-2.25 w-px -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink-3/50"
            style={{ left: `${defaultPct}%` }}
          />
        )}
        <div
          className={`pointer-events-none absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white transition-[box-shadow,scale] duration-120 ${
            dragging
              ? "scale-110 shadow-[0_1px_3px_rgba(16,18,24,.3),0_0_0_1.5px_var(--color-accent),0_0_0_5px_rgba(43,108,255,.22)]"
              : "shadow-[0_1px_3px_rgba(16,18,24,.3),0_0_0_1.5px_var(--color-accent)] group-hover/track:shadow-[0_1px_3px_rgba(16,18,24,.3),0_0_0_1.5px_var(--color-accent),0_0_0_4px_rgba(43,108,255,.15)]"
          }`}
          style={{ left: `${pct}%` }}
        />
        {/* Native range input overlaid transparently — owns keyboard + pointer
            interaction while the styled track/fill/thumb above render the look. */}
        <input
          type="range"
          min={entry.min}
          max={entry.max}
          step={entry.step}
          value={local}
          onChange={handleChange}
          onPointerDown={() => setDragging(true)}
          onPointerUp={() => onCommit(paramKey, local)}
          aria-label={titleCase(paramKey)}
          aria-describedby={hasDesc ? descId : undefined}
          className="absolute inset-x-0 top-1/2 m-0 h-3.5 w-full -translate-y-1/2 cursor-pointer appearance-none bg-transparent [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-transparent"
        />
      </div>
    </div>
  );
}
