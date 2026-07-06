import type React from "react";
import { useDismiss } from "../../hooks/useDismiss";

/**
 * ModalShell — a centered, frosted modal over a dimmed backdrop. Closes on
 * backdrop click + Escape (via {@link useDismiss}). Matches the design
 * language (hairline border, soft float shadow, 12px radius).
 */
export function ModalShell({
  onClose,
  children,
  labelledBy,
}: {
  onClose: () => void;
  children: React.ReactNode;
  labelledBy: string;
}) {
  const ref = useDismiss<HTMLDivElement>(true, onClose);
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-[rgba(18,20,28,.34)] px-5 backdrop-blur-xs">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className="animate-rise w-full max-w-110 rounded-panel border border-line-2 bg-surface p-5 shadow-float"
      >
        {children}
      </div>
    </div>
  );
}
