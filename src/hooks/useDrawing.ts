/**
 * useDrawing — generate a 2D technical drawing of the current model. Mirrors
 * useExport: open a native Save dialog for the PDF (the engine writes the SVG
 * alongside), call the engine, and show a transient result toast. References are
 * excluded engine-side; this hook just drives the save + feedback.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";

import { engineCreateDrawing } from "../lib/ipc/engine";
import { getExportDir } from "../lib/ipc/workspace";
import { tildePath } from "../lib/workspaces";

export interface DrawingNote {
  kind: "ok" | "err";
  text: string;
}

export function useDrawing() {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<DrawingNote | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flash = useCallback((n: DrawingNote) => {
    setNote(n);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setNote(null), 3200);
  }, []);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const createDrawing = useCallback(async () => {
    setBusy(true);
    try {
      const dir = await getExportDir();
      const fallback = `${dir}/drawing.pdf`;
      let target: string | null;
      try {
        target = await save({
          defaultPath: fallback,
          filters: [{ name: "Technical drawing (PDF)", extensions: ["pdf"] }],
        });
      } catch {
        target = fallback;
      }
      if (target === null) return; // cancelled

      const res = await engineCreateDrawing(target);
      const extra = res.note ? ` ${res.note}` : "";
      flash({ kind: "ok", text: `Drawing saved to ${tildePath(target)}.${extra}` });
    } catch {
      flash({ kind: "err", text: "Could not generate the drawing." });
    } finally {
      setBusy(false);
    }
  }, [flash]);

  return { busy, note, createDrawing };
}
