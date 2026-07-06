/**
 * useImport — the shared CAD-import flow used by the TopBar Import button and the
 * Viewport drag-drop / empty-state CTA. Imports an external STEP/STP/BREP/STL as
 * a ghosted reference fixture (engine copies it into the workspace, records it in
 * imports.json, rebuilds). The viewport refreshes on the engine's model-updated
 * event, so the hook only owns a transient result toast (auto-clearing) and an
 * in-flight marker, mirroring useExport.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { engineImportReference, pickCadFile } from "../lib/ipc";

/** A transient import result note, shown briefly inline. */
export interface ImportNote {
  kind: "ok" | "err";
  text: string;
}

/** Extensions the importer accepts (mirrors the engine loader + Rust filter). */
export const IMPORT_EXTENSIONS = ["step", "stp", "brep", "stl"] as const;

function baseName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

export function isSupportedImport(path: string): boolean {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return (IMPORT_EXTENSIONS as readonly string[]).includes(ext);
}

export function useImport() {
  const [importing, setImporting] = useState(false);
  const [note, setNote] = useState<ImportNote | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flash = useCallback((n: ImportNote) => {
    setNote(n);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setNote(null), 2600);
  }, []);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const importPath = useCallback(
    async (path: string) => {
      if (!isSupportedImport(path)) {
        flash({ kind: "err", text: `Unsupported file. ${baseName(path)}` });
        return;
      }
      setImporting(true);
      try {
        await engineImportReference(path);
        flash({ kind: "ok", text: `Imported ${baseName(path)}` });
      } catch {
        flash({ kind: "err", text: `Import failed. ${baseName(path)}` });
      } finally {
        setImporting(false);
      }
    },
    [flash],
  );

  const pickAndImport = useCallback(async () => {
    const path = await pickCadFile();
    if (path) await importPath(path);
  }, [importPath]);

  return { importing, note, importPath, pickAndImport };
}
