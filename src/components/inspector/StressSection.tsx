/**
 * StressSection — the Checks tab's first-order stress hot-spots (sharp internal
 * corners), severity-dotted; each row selects its part. Honest about being a
 * geometric heuristic. Report state is owned by ChecksPanel.
 */
import type { StressState } from "../../hooks/useStress";
import type { StressHotspot, StressSeverity } from "../../lib/validation";

const DOT: Record<StressSeverity, string> = {
  warning: "bg-amber",
  advisory: "bg-ink-3",
};

function HotspotRow({
  h,
  selected,
  onClick,
}: {
  h: StressHotspot;
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
      <span className={`mt-1.25 h-2 w-2 shrink-0 rounded-full ${DOT[h.severity]}`} />
      <span className="min-w-0 flex-1">
        <span className="block text-body text-ink">{h.message}</span>
        <span className="mt-0.5 block text-caption text-ink-3">{h.hint}</span>
      </span>
    </button>
  );
}

export default function StressSection({
  state,
  selectedId,
  onSelectPart,
}: {
  state: StressState;
  selectedId: string | null;
  onSelectPart: (id: string | null) => void;
}) {
  const { report, loading, error } = state;

  const counts = report?.summary ?? { warning: 0, advisory: 0, parts: 0 };
  const total = counts.warning + counts.advisory;
  const multiPart = (report?.parts.filter((p) => p.hotspots.length > 0).length ?? 0) > 1;

  return (
    <div className="pb-1.5">
      <p className="px-3.5 pb-1.5 pt-0.5 text-caption text-ink-3">
        Where load concentrates, not a solved stress field.
        {report && total === 0 && " No stress risks found."}
        {!report && loading && " Checking…"}
      </p>
      {error && !report && <p className="px-3.5 py-1.5 text-caption text-ink-3">{error}</p>}
      {report?.parts.map((part) =>
        part.hotspots.length === 0 ? null : (
          <div key={part.partId}>
            {multiPart && (
              <div className="px-3.5 pb-1 pt-2 text-micro font-bold uppercase tracking-eyebrow text-ink-3">
                {part.partName}
              </div>
            )}
            {part.hotspots.map((h, i) => {
              const selected = selectedId === part.partId;
              return (
                <HotspotRow
                  key={`${part.partId}-${i}`}
                  h={h}
                  selected={selected}
                  onClick={() => onSelectPart(selected ? null : part.partId)}
                />
              );
            })}
          </div>
        ),
      )}
    </div>
  );
}
