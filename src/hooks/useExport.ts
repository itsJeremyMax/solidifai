/**
 * useExport — the single shared model-export flow used by BOTH the TopBar
 * "Export" dialog and the Inspector's STEP / STL / GLB quick chips.
 *
 * Flow for a given `formatKey` (engine format) + `ext` (file extension):
 *   1. Resolve the workspace's `exports/` folder (created on demand) and open a
 *      native Save dialog (`@tauri-apps/plugin-dialog`'s `save`) defaulting to
 *      `<workspaceDir>/exports/model.<ext>` with an extension filter.
 *   2. If the user picks a path → `engineExport(formatKey, path, options)` → success toast.
 *   3. If the user cancels (save resolves `null`) → no-op, no toast.
 *   4. If the Save dialog throws / is unavailable → fall back to exporting
 *      directly to `<workspaceDir>/model.<ext>` so export still works.
 *   5. Any `engineExport` failure → error toast.
 *
 * The hook owns a small transient `note` (auto-clearing after ~2.6s) and an
 * `exporting` marker (the in-flight format, for disabling/spinners). Each
 * consumer calls the hook independently — there's no shared cross-component
 * state, just one DRY implementation of the dialog + fallback + toast logic.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";

import { engineExport, getExportDir } from "../lib/ipc";
import { tildePath } from "../lib/workspaces";

/** A transient export result note (success or failure), shown briefly inline. */
export interface ExportNote {
  kind: "ok" | "err";
  text: string;
}

/** Human label for a format, for the save-dialog filter + error text. */
const FORMAT_LABEL: Record<string, string> = {
  step: "STEP",
  stl: "STL",
  glb: "glTF Binary",
  gltf: "glTF",
  brep: "BREP",
  "3mf": "3MF",
};

export interface UseExportResult {
  /** The format currently exporting, or `null` when idle. */
  exporting: string | null;
  /** The latest transient note, or `null`. Auto-clears after ~2.6s. */
  note: ExportNote | null;
  /**
   * Run the export flow. `formatKey` is the engine format string (e.g. "step",
   * "stl", "glb", "gltf", "brep", "3mf"); `ext` is the file extension for the
   * save dialog; `options` is the optional per-format settings dict. Quick
   * one-click callers pass `runExport(ext, ext)` for engine defaults. Never throws.
   */
  runExport: (formatKey: string, ext: string, options?: Record<string, unknown>) => Promise<void>;
}

export function useExport(): UseExportResult {
  const [exporting, setExporting] = useState<string | null>(null);
  const [note, setNote] = useState<ExportNote | null>(null);
  const noteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (noteTimer.current) clearTimeout(noteTimer.current);
    },
    [],
  );

  const flash = useCallback((n: ExportNote) => {
    setNote(n);
    if (noteTimer.current) clearTimeout(noteTimer.current);
    noteTimer.current = setTimeout(() => setNote(null), 2600);
  }, []);

  const runExport = useCallback(
    async (formatKey: string, ext: string, options?: Record<string, unknown>) => {
      const label = FORMAT_LABEL[formatKey] ?? formatKey.toUpperCase();
      setExporting(formatKey);
      try {
        const dir = await getExportDir();
        const fallbackPath = `${dir}/model.${ext}`;

        // Prefer a native Save dialog; if it throws (plugin unavailable) we
        // fall back to writing directly into the workspace dir.
        let target: string | null;
        try {
          target = await save({
            defaultPath: fallbackPath,
            filters: [{ name: label, extensions: [ext] }],
          });
        } catch {
          target = fallbackPath;
        }

        if (target === null) return;

        await engineExport(formatKey, target, options);
        flash({ kind: "ok", text: `Exported to ${tildePath(target)}` });
      } catch {
        flash({ kind: "err", text: `Export failed. ${label}` });
      } finally {
        setExporting(null);
      }
    },
    [flash],
  );

  return { exporting, note, runExport };
}
