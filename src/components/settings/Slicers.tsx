/**
 * Slicers — the "Slicers" settings section. Lists the supported slicers with
 * their detected status (path + version), and lets the user point a slicer at a
 * custom binary when it lives somewhere unusual. Provider-agnostic: it renders
 * one card per entry from `get_slicer_config`, so new slicers appear here with no
 * change. The override is persisted app-side and read by the engine too, so slice
 * estimates and "open in slicer" use the same binary.
 */
import { useEffect, useState } from "react";
import { FolderOpen, Printer, RotateCcw } from "lucide-react";

import { getSlicerConfig, pickSlicerBinary, setSlicerOverride } from "../../lib/ipc/fabrication";
import type { SlicerEntry } from "../../lib/fabrication";

const ICON_STROKE = 1.7;
const ENGINE_HALO = "0 0 0 4px rgba(25,169,87,.14)";

/** Detected (green, with version) or Not detected (muted) chip. */
function StatusPill({ entry }: { entry: SlicerEntry }) {
  if (entry.found) {
    return (
      <span className="inline-flex shrink-0 items-center gap-1.75 rounded-full border border-line-2 bg-surface px-2.5 py-1 text-caption font-medium text-ink-2">
        <span className="h-2 w-2 rounded-full bg-engine" style={{ boxShadow: ENGINE_HALO }} />
        Detected{entry.version ? ` · ${entry.version}` : ""}
      </span>
    );
  }
  return (
    <span className="inline-flex shrink-0 items-center gap-1.75 rounded-full border border-line-2 bg-surface px-2.5 py-1 text-caption font-medium text-ink-3">
      <span className="h-2 w-2 rounded-full bg-ink-3" />
      Not detected
    </span>
  );
}

/** One slicer card: header + status, then an editable binary-path field. */
function SlicerCard({
  entry,
  onChanged,
}: {
  entry: SlicerEntry;
  onChanged: (next: SlicerEntry[]) => void;
}) {
  const [draft, setDraft] = useState(entry.overridePath ?? "");
  const [busy, setBusy] = useState(false);

  // Re-sync when the saved override changes (after a save or reset elsewhere).
  useEffect(() => setDraft(entry.overridePath ?? ""), [entry.overridePath]);

  const save = async (value: string | null) => {
    setBusy(true);
    try {
      onChanged(await setSlicerOverride(entry.id, value));
    } catch {
      // Leave the field as-is; the row still reflects the last good config.
    } finally {
      setBusy(false);
    }
  };

  const commit = () => {
    const next = draft.trim();
    if (next === (entry.overridePath ?? "")) return; // no change
    void save(next || null);
  };

  const browse = async () => {
    const picked = await pickSlicerBinary();
    if (picked) {
      setDraft(picked);
      void save(picked);
    }
  };

  return (
    <div className="overflow-hidden rounded-panel border border-line bg-surface">
      <div className="flex items-center gap-2.5 px-4 py-3.5">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-line-2 bg-surface-2 text-accent">
          <Printer size={17} strokeWidth={ICON_STROKE} />
        </span>
        <span className="flex-1 truncate text-base font-semibold tracking-snug text-ink">
          {entry.label}
        </span>
        <StatusPill entry={entry} />
      </div>

      <div className="border-t border-line px-4 py-3.5">
        <div className="flex items-center justify-between">
          <span className="text-micro uppercase tracking-eyebrow text-ink-3">Binary</span>
          {entry.overridePath && (
            <button
              type="button"
              onClick={() => {
                setDraft("");
                void save(null);
              }}
              className="inline-flex items-center gap-1.25 text-caption font-medium text-ink-3 transition-colors duration-150 hover:text-ink"
            >
              <RotateCcw size={12} strokeWidth={2} />
              Reset to auto-detected
            </button>
          )}
        </div>

        <div className="mt-1.75 flex items-center gap-2">
          <input
            type="text"
            value={draft}
            spellCheck={false}
            placeholder={entry.executable ?? "Path to the slicer binary"}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
            }}
            className="h-9 min-w-0 flex-1 rounded-lg border border-line-2 bg-surface-2 px-3 font-mono text-caption text-ink outline-none transition-colors duration-150 placeholder:font-mono placeholder:text-ink-3 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint"
          />
          <button
            type="button"
            onClick={browse}
            disabled={busy}
            className="inline-flex h-9 shrink-0 items-center gap-1.75 rounded-lg border border-line-2 bg-surface px-3 text-body font-medium text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink disabled:opacity-50"
          >
            <FolderOpen size={14} strokeWidth={ICON_STROKE} />
            Browse
          </button>
        </div>

        <p className="mt-2 text-caption leading-relaxed text-ink-3">
          {entry.overridePath
            ? "Using your custom path. Reset to fall back to auto-detection."
            : entry.found
              ? "Auto-detected. Set a path only if you want a specific install."
              : `${entry.label} was not found in the usual location. Set its binary path to enable slicing.`}
        </p>
      </div>
    </div>
  );
}

export default function Slicers() {
  const [slicers, setSlicers] = useState<SlicerEntry[] | null>(null); // null = loading

  useEffect(() => {
    let live = true;
    getSlicerConfig()
      .then((list) => live && setSlicers(list))
      .catch(() => live && setSlicers([]));
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="mx-auto max-w-160 py-6.5">
      <h2 className="text-base font-bold tracking-snug text-ink">Slicers</h2>
      <p className="mt-1.25 text-body leading-normal text-ink-2">
        Connect a slicer to use your printer and filament profiles, estimate prints, and open models
        for slicing. Set a custom path if yours isn't detected.
      </p>

      {slicers === null ? (
        <div className="mt-4.5 text-body text-ink-3">Loading…</div>
      ) : slicers.length === 0 ? (
        <div className="mt-4.5 rounded-panel border border-dashed border-line-2 bg-surface-2 px-4 py-4.5 text-center text-body text-ink-3">
          No supported slicers yet.
        </div>
      ) : (
        <div className="mt-4.5 space-y-3.5">
          {slicers.map((s) => (
            <SlicerCard key={s.id} entry={s} onChanged={setSlicers} />
          ))}
        </div>
      )}
    </div>
  );
}
