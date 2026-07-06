/**
 * Bind ⌘Z → undo and ⇧⌘Z → redo (Ctrl on non-mac), but only when the user is
 * NOT typing in an input/textarea/contenteditable (so the inline param editor
 * and the terminal keep their own undo). After the engine rebuilds, the existing
 * `model-updated` flow refreshes the viewport — nothing else to do here.
 */
import { useEffect } from "react";

import { engineRedo, engineUndo } from "../lib/ipc";

function isTextEntry(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
}

export function useHistoryKeys(): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod || e.key.toLowerCase() !== "z") return;
      if (isTextEntry(e.target)) return;
      e.preventDefault();
      if (e.shiftKey) void engineRedo();
      else void engineUndo();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
