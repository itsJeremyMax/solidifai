/**
 * useImport — the shared CAD-import flow used by the TopBar Import button and the
 * Viewport drag-drop / empty-state CTA. Imports an engine-supported file as a
 * ghosted reference fixture (engine copies it into the workspace, records it in
 * imports.json, rebuilds). The viewport refreshes on the engine's model-updated
 * event, so the hook only owns a transient result toast (auto-clearing) and an
 * in-flight marker, mirroring useExport.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { engineGetImportCapabilities, engineImportReference, pickCadFile } from "../lib/ipc/engine";

/** A transient import result note, shown briefly inline. */
export interface ImportNote {
  kind: "ok" | "err";
  text: string;
}

/** Startup fallback while capability RPC is unavailable. */
export const LEGACY_IMPORT_EXTENSIONS = ["step", "stp", "brep", "stl"] as const;

export function normalizeImportExtensions(capabilities: string | null): string[] {
  try {
    const formats = JSON.parse(capabilities ?? "{}").formats as Record<
      string,
      { extensions?: unknown }
    >;
    const extensions = Object.values(formats).flatMap(({ extensions }) =>
      Array.isArray(extensions)
        ? extensions.filter((extension): extension is string => typeof extension === "string")
        : [],
    );
    const normalized = [
      ...new Set(extensions.map((extension) => extension.replace(/^\./, "").toLowerCase())),
    ];
    return normalized.length ? normalized : [...LEGACY_IMPORT_EXTENSIONS];
  } catch {
    return [...LEGACY_IMPORT_EXTENSIONS];
  }
}

function baseName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

export function isSupportedImport(
  path: string,
  extensions: readonly string[] = LEGACY_IMPORT_EXTENSIONS,
): boolean {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return extensions.includes(ext);
}

export function useImport() {
  const [importing, setImporting] = useState(false);
  const [note, setNote] = useState<ImportNote | null>(null);
  const [extensions, setExtensions] = useState<string[]>([...LEGACY_IMPORT_EXTENSIONS]);
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

  useEffect(() => {
    let active = true;
    void engineGetImportCapabilities().then((capabilities) => {
      if (active) setExtensions(normalizeImportExtensions(capabilities));
    });
    return () => {
      active = false;
    };
  }, []);

  const importPath = useCallback(
    async (path: string) => {
      if (!isSupportedImport(path, extensions)) {
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
    [extensions, flash],
  );

  const pickAndImport = useCallback(async () => {
    const path = await pickCadFile(extensions);
    if (path) await importPath(path);
  }, [extensions, importPath]);

  return { importing, note, importPath, pickAndImport, extensions };
}
