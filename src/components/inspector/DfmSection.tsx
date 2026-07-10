/**
 * DfmSection — the Checks tab's manufacturability report body: per-part groups
 * of violations; each row selects its part in the viewport. Report state is
 * owned by ChecksPanel (shared health strip + header re-run).
 */
import { RotateCw, TriangleAlert } from "lucide-react";

import type { DfmState } from "../../hooks/useDfm";
import { DFM_SEVERITIES, type DfmSeverity, type DfmViolation } from "../../lib/dfm";

const DOT: Record<DfmSeverity, string> = {
  critical: "bg-danger-bold",
  warning: "bg-amber",
  advisory: "bg-ink-3",
};

/* One violation: severity dot + message, with the measured value vs the limit. */
function ViolationRow({
  v,
  selected,
  onClick,
}: {
  v: DfmViolation;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        selected
          ? "flex w-full items-start gap-2.5 bg-accent-tint px-3.5 py-2 text-left shadow-[inset_2px_0_0_var(--color-accent)]"
          : "flex w-full items-start gap-2.5 px-3.5 py-2 text-left transition-colors hover:bg-surface-2"
      }
    >
      <span className={`mt-1.25 h-2 w-2 shrink-0 rounded-full ${DOT[v.severity]}`} />
      <span className="min-w-0 flex-1">
        <span className="block text-body text-ink">{v.message}</span>
        <span className="mt-0.5 block font-mono text-caption text-ink-3">
          {v.measured.value} {v.measured.unit} · limit {v.threshold.value} {v.threshold.unit}
          {v.sampled ? " · sampled" : ""}
        </span>
      </span>
    </button>
  );
}

/* A pulsing bar placeholder for the loading skeleton. */
function Bar({ className }: { className: string }) {
  return <div className={`rounded-full bg-line-2 ${className}`} />;
}

/* Structural skeleton mirroring the section's own shape (grouped rows). */
function LoadingSkeleton() {
  return (
    <div className="animate-pulse pb-2" role="status" aria-label="Analyzing the model">
      {[0, 1].map((g) => (
        <div key={g}>
          <div className="px-3.5 pb-1.75 pt-2.75">
            <Bar className="h-2 w-20" />
          </div>
          {[0, 1].map((r) => (
            <div key={r} className="flex items-start gap-2.5 px-3.5 py-2">
              <Bar className="mt-1.25 h-2 w-2 shrink-0" />
              <div className="min-w-0 flex-1">
                <Bar className={r === 0 ? "h-2.5 w-4/5" : "h-2.5 w-3/5"} />
                <div className="mt-1.5">
                  <Bar className="h-2 w-1/3" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export default function DfmSection({
  state,
  selectedId,
  onSelectPart,
}: {
  state: DfmState;
  selectedId: string | null;
  onSelectPart: (id: string | null) => void;
}) {
  const { report, loading, error, refresh } = state;

  if (loading && !report) return <LoadingSkeleton />;
  if (error && !report)
    return (
      <div className="flex flex-col items-start gap-2.5 px-3.5 py-2.5">
        <span className="flex items-center gap-2 text-body text-ink-2">
          <TriangleAlert size={14} strokeWidth={1.9} className="shrink-0 text-amber" />
          {error}
        </span>
        <button
          type="button"
          onClick={refresh}
          className="inline-flex items-center gap-1.5 rounded-md border border-line-2 bg-surface px-2.5 py-1 text-caption font-medium text-ink-2 transition-colors hover:border-line-3 hover:text-ink"
        >
          <RotateCw size={12} strokeWidth={2} />
          Try again
        </button>
      </div>
    );
  if (!report) return null;

  const total = report.summary.critical + report.summary.warning + report.summary.advisory;
  const anyEvaluated = report.parts.some((p) => p.evaluated);

  return (
    <div className="pb-2">
      {total === 0 && (
        <p className="px-3.5 pb-1.5 pt-0.5 text-caption text-ink-3">
          {anyEvaluated
            ? "No manufacturability issues found."
            : "Nothing to check for this process yet."}
        </p>
      )}

      {/* per-part groups */}
      {report.parts.map((part) => {
        if (!part.evaluated) {
          return (
            <div key={part.partId} className="px-3.5 py-2 text-caption text-ink-3">
              <span className="text-ink-2">{part.partName}</span>
              <span className="ml-1.5">{part.note}</span>
            </div>
          );
        }
        if (part.violations.length === 0) return null;
        const selected = selectedId === part.partId;
        const sorted = DFM_SEVERITIES.flatMap((s) =>
          part.violations.filter((v) => v.severity === s),
        );
        return (
          <div key={part.partId}>
            <div className="flex items-center gap-2 px-3.5 pb-1.75 pt-2.75 text-micro font-bold uppercase tracking-eyebrow text-ink-3">
              <span>{part.partName}</span>
              <span className="font-mono text-caption tracking-normal text-ink-3">
                {part.violations.length}
              </span>
            </div>
            {sorted.map((v, i) => (
              <ViolationRow
                key={`${part.partId}-${v.rule}-${i}`}
                v={v}
                selected={selected}
                onClick={() => onSelectPart(selected ? null : part.partId)}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
