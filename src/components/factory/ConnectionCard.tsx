import { Printer } from "lucide-react";
import type { Destination } from "../../lib/fabrication";

const PROVIDER_LABELS: Record<string, string> = { orca: "OrcaSlicer" };

/** One saved connection in the Factory grid. Click to edit. */
export default function ConnectionCard({
  dest,
  onClick,
}: {
  dest: Destination;
  onClick: () => void;
}) {
  const profiles = [dest.printerProfile, dest.filamentProfile, dest.processProfile]
    .filter(Boolean)
    .join(" · ");
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex flex-col gap-2.5 rounded-[15px] border border-line-2 bg-surface px-4 py-4 text-left shadow-card transition-[transform,border-color,box-shadow] duration-200 ease-out-soft hover:-translate-y-0.5 hover:border-accent-line hover:shadow-float"
    >
      <div className="flex items-center gap-2.5">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-line-2 bg-surface-2 text-ink-3 transition-colors duration-200 group-hover:border-accent group-hover:bg-accent-tint group-hover:text-accent">
          <Printer size={18} strokeWidth={1.6} />
        </span>
        <div className="min-w-0">
          <div className="truncate text-body font-semibold text-ink">{dest.name}</div>
          <div className="truncate text-caption text-ink-3">
            {PROVIDER_LABELS[dest.provider] ?? dest.provider}
          </div>
        </div>
      </div>
      {profiles && <div className="truncate font-mono text-caption text-ink-3">{profiles}</div>}
    </button>
  );
}
