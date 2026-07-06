import { useEffect, useRef } from "react";
import { Archive, X } from "lucide-react";

const ICON_STROKE = 1.7;
/** How long the toast lingers before auto-dismissing (ms). */
const AUTO_DISMISS_MS = 6000;

interface ArchiveToastProps {
  name: string;
  onUndo: () => void;
  onDismiss: () => void;
}

export function ArchiveToast({ name, onUndo, onDismiss }: ArchiveToastProps) {
  // Keep a stable ref to the latest onDismiss. The caller passes an inline lambda
  // that changes identity on every render (and HomeView re-renders right after
  // showing the toast), so depending on onDismiss directly would re-arm — and
  // perpetually reset — the auto-dismiss timer.
  const onDismissRef = useRef(onDismiss);
  useEffect(() => {
    onDismissRef.current = onDismiss;
  });

  // Auto-dismiss after AUTO_DISMISS_MS. Arms only on `name` change so a
  // subsequent archive action resets the countdown, and a plain re-render
  // (new onDismiss reference) does not.
  useEffect(() => {
    const id = window.setTimeout(() => onDismissRef.current(), AUTO_DISMISS_MS);
    return () => window.clearTimeout(id);
  }, [name]);

  return (
    <div
      role="status"
      aria-live="polite"
      className="motion-safe:animate-rise fixed bottom-6 left-1/2 z-50 -translate-x-1/2"
    >
      <div className="flex items-center gap-2.5 rounded-full border border-term-line bg-term px-4 py-2.5 shadow-float">
        {/* Archive icon — dimmed on the dark surface */}
        <Archive size={15} strokeWidth={ICON_STROKE} className="shrink-0 text-term-ink-dim" />

        {/* Message */}
        <span className="text-body text-term-ink">
          Archived <strong className="font-semibold text-term-ink-bright">{name}</strong>
        </span>

        {/* Undo link — cobalt accent */}
        <button
          type="button"
          aria-label="Undo"
          onClick={onUndo}
          className="ml-0.5 text-body font-semibold text-accent transition-colors duration-150 hover:text-accent-press"
        >
          Undo
        </button>

        {/* Separator hairline */}
        <span className="h-4 w-px shrink-0 bg-term-line" aria-hidden="true" />

        {/* Dismiss */}
        <button
          type="button"
          aria-label="Dismiss"
          onClick={onDismiss}
          className="grid h-5 w-5 shrink-0 place-items-center rounded-full text-term-ink-dim transition-colors duration-150 hover:text-term-ink"
        >
          <X size={13} strokeWidth={ICON_STROKE} />
        </button>
      </div>
    </div>
  );
}
