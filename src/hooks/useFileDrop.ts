/**
 * useFileDrop — listens for a CAD file dragged onto the window (Tauri v2's
 * window-level onDragDropEvent) and reports the dragging state plus the dropped
 * path. Only supported extensions trigger onDrop; the dragging flag drives the
 * viewport's drop-hint overlay.
 */
import { useEffect, useRef, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";

import { LEGACY_IMPORT_EXTENSIONS } from "./useImport";

export function firstSupported(
  paths: string[],
  extensions: readonly string[] = LEGACY_IMPORT_EXTENSIONS,
): string | undefined {
  return paths.find((path) => extensions.includes((path.split(".").pop() ?? "").toLowerCase()));
}

export function useFileDrop(
  onDrop: (path: string) => void,
  extensions: readonly string[] = LEGACY_IMPORT_EXTENSIONS,
): boolean {
  const [dragging, setDragging] = useState(false);
  const onDropRef = useRef(onDrop);
  onDropRef.current = onDrop;
  const extensionsRef = useRef(extensions);
  extensionsRef.current = extensions;

  useEffect(() => {
    let cancelled = false;
    let unlisten: (() => void) | undefined;

    getCurrentWebview()
      .onDragDropEvent((event) => {
        const p = event.payload;
        if (p.type === "enter" || p.type === "over") {
          setDragging(true);
        } else if (p.type === "drop") {
          setDragging(false);
          const match = firstSupported(p.paths, extensionsRef.current);
          if (match) onDropRef.current(match);
        } else {
          setDragging(false); // leave / cancel
        }
      })
      .then((fn) => {
        if (cancelled) fn();
        else unlisten = fn;
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  return dragging;
}
