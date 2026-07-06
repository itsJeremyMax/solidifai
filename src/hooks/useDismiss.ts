/**
 * useDismiss — close a popover/menu/dialog on outside-click or Escape.
 *
 * Returns a ref to attach to the popover's root element. While `open`, a
 * `mousedown` outside that element or an `Escape` keypress invokes `onClose`.
 * Listeners are only attached while open and torn down on close/unmount.
 *
 * Shared by the top-bar dropdowns (workspace switcher, export menu) and the
 * launcher's per-workspace menu + rename/delete dialogs so the dismiss
 * behavior is implemented once.
 */
import { useEffect, useRef } from "react";

export function useDismiss<T extends HTMLElement = HTMLDivElement>(
  open: boolean,
  onClose: () => void,
) {
  const ref = useRef<T>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  return ref;
}
