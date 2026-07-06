/**
 * EngineStatusPill — status dot + label, with build details in a click-to-open
 * popover. While the engine is downloading (`updating`) a thin fill across the
 * chip's base and a percentage track the download.
 */
import { useCallback, useState } from "react";

import { useEngineStatus } from "../hooks/useEngineStatus";
import { useDismiss } from "../hooks/useDismiss";
import type { EngineStatus } from "../lib/ipc";

/** Tailwind dot color per engine status. */
const DOT_COLOR: Record<EngineStatus, string> = {
  provisioning: "bg-amber",
  updating: "bg-amber",
  ready: "bg-engine",
  error: "bg-danger-bold",
};

/** Soft halo ring around the dot (matches the mockup's pulse glow), per status. */
const DOT_RING: Record<EngineStatus, string> = {
  provisioning: "0 0 0 4px rgba(224,162,59,.14)",
  updating: "0 0 0 4px rgba(224,162,59,.14)",
  ready: "0 0 0 4px rgba(25,169,87,.14)",
  error: "0 0 0 4px rgba(229,72,77,.14)",
};

/** One label/value line in the detail card. The value is mono and truncates. */
function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 px-3 py-1.5">
      <span className="shrink-0 text-caption text-ink-3">{label}</span>
      <span className="truncate font-mono text-caption text-ink-2" title={value}>
        {value}
      </span>
    </div>
  );
}

export default function EngineStatusPill() {
  const { status, label, version, interpreter, message, progress } = useEngineStatus();
  const [open, setOpen] = useState(false);
  const ref = useDismiss<HTMLDivElement>(
    open,
    useCallback(() => setOpen(false), []),
  );
  const updating = status === "updating";
  const pct = progress != null ? Math.round(progress * 100) : null;

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        // Hover surfaces the build string; click opens the full card.
        title={version ? `${label} · ${version}` : label}
        className="relative inline-flex h-7.5 items-center gap-2 overflow-hidden whitespace-nowrap rounded-full border border-line-2 bg-[linear-gradient(180deg,#fff,#fafaf8)] px-2.75 text-xs font-medium text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink"
      >
        <span
          className={`h-2 w-2 rounded-full ${DOT_COLOR[status]} ${
            status === "ready" || updating ? "animate-engine-pulse" : ""
          }`}
          style={{ boxShadow: DOT_RING[status] }}
        />
        {label}
        {updating && pct != null && (
          <span className="font-mono text-caption text-ink-3">{pct}%</span>
        )}
        {updating && (
          <span
            aria-hidden
            className="absolute bottom-0 left-0 h-0.5 bg-engine transition-[width] duration-300 ease-out"
            style={{ width: pct != null ? `${pct}%` : "15%" }}
          />
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Engine details"
          className="animate-rise absolute left-0 top-9.5 z-30 w-76 overflow-hidden rounded-panel border border-line-2 bg-surface shadow-float"
        >
          {/* Card header: the live status, restated. */}
          <div className="flex items-center gap-2 border-b border-line-2 px-3 py-2.5">
            <span
              className={`h-2 w-2 rounded-full ${DOT_COLOR[status]}`}
              style={{ boxShadow: DOT_RING[status] }}
            />
            <span className="text-body font-medium text-ink">{label}</span>
          </div>

          {/* Detail rows — whichever facts the engine has resolved so far. */}
          <div className="py-1">
            {version && <DetailRow label="Runtime" value={version} />}
            {interpreter && <DetailRow label="Interpreter" value={interpreter} />}
            {status === "error" && message && (
              <p className="px-3 py-1.5 text-caption text-danger">{message}</p>
            )}
            {!version && !interpreter && status !== "error" && (
              <p className="px-3 py-2 text-caption text-ink-3">Resolving the Python interpreter…</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
