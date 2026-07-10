/**
 * ChecksPanel — the Inspector's Checks tab: one glanceable health strip over
 * Goals, Manufacturability (DFM), Stress, and Fit check sections. The reports
 * are lazily computed + cached per build; opening this tab is the trigger.
 */
import { RotateCw } from "lucide-react";

import CollapsibleSection from "./CollapsibleSection";
import GoalsSection from "./GoalsSection";
import DfmSection from "./DfmSection";
import StressSection from "./StressSection";
import FitCheckSection from "./FitCheckSection";
import { useRequirements } from "../../hooks/useRequirements";
import { useDfm } from "../../hooks/useDfm";
import { useStress } from "../../hooks/useStress";
import type { SectionKey, SectionState } from "../../state/useInspectorPrefs";

function Chip({ dot, label, tone }: { dot: string; label: string; tone: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-caption ${tone}`}>
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {label}
    </span>
  );
}

/** Re-run button for a section header (sibling of the toggle, never nested). */
function RerunAction({ loading, onRun }: { loading: boolean; onRun: () => void }) {
  return (
    <button
      type="button"
      title="Re-run check"
      aria-label="Re-run check"
      disabled={loading}
      onClick={(e) => {
        e.stopPropagation();
        onRun();
      }}
      className="grid h-4.5 w-4.5 place-items-center rounded-sm text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink disabled:hover:bg-transparent disabled:hover:text-ink-3"
    >
      <RotateCw size={12} strokeWidth={2} className={loading ? "animate-spin" : ""} />
    </button>
  );
}

export default function ChecksPanel({
  buildId,
  active,
  hasParams,
  selectedId,
  onSelectPart,
  open,
  onToggleSection,
}: {
  buildId: number;
  active: boolean;
  hasParams: boolean;
  selectedId: string | null;
  onSelectPart: (id: string | null) => void;
  open: SectionState;
  onToggleSection: (k: SectionKey) => void;
}) {
  const req = useRequirements(buildId, active && buildId >= 0);
  const dfm = useDfm(buildId, active && buildId >= 0);
  const stress = useStress(buildId, active && buildId >= 0);

  if (buildId < 0) {
    return (
      <p className="px-3.5 py-3.5 text-body text-ink-3">
        Build a model to check it against goals, manufacturability, and stress.
      </p>
    );
  }

  const goals = req.report?.summary;
  const hasGoals = (req.report?.requirements.length ?? 0) > 0;
  const dfmTotal = dfm.report
    ? dfm.report.summary.critical + dfm.report.summary.warning + dfm.report.summary.advisory
    : null;
  const dfmEvaluated = dfm.report?.parts.some((p) => p.evaluated) ?? false;
  const stressTotal = stress.report
    ? stress.report.summary.warning + stress.report.summary.advisory
    : null;

  const anyLoading = req.loading || dfm.loading || stress.loading;
  const allLoaded = dfm.report !== null && stress.report !== null;
  const goalsPass = !hasGoals || goals?.allMet === true;
  const allClean = allLoaded && goalsPass && dfmEvaluated && dfmTotal === 0 && stressTotal === 0;

  return (
    <div className="pb-2">
      {/* health strip */}
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-3.5 py-2.5">
        {allClean ? (
          <Chip dot="bg-engine" label="All checks pass" tone="text-engine" />
        ) : (
          <>
            {hasGoals && goals && (
              <Chip
                dot={goals.allMet ? "bg-engine" : "bg-amber"}
                label={`${goals.met}/${goals.total} goals`}
                tone={goals.allMet ? "text-engine" : "text-ink-2"}
              />
            )}
            {dfmTotal !== null && dfmEvaluated && (
              <Chip
                dot={
                  dfm.report!.summary.critical > 0
                    ? "bg-danger-bold"
                    : dfmTotal > 0
                      ? "bg-amber"
                      : "bg-engine"
                }
                label={dfmTotal > 0 ? `${dfmTotal} DFM` : "DFM clear"}
                tone={dfmTotal > 0 ? "text-ink-2" : "text-engine"}
              />
            )}
            {stressTotal !== null && (
              <Chip
                dot={stressTotal > 0 ? "bg-amber" : "bg-engine"}
                label={stressTotal > 0 ? `${stressTotal} stress` : "Stress clear"}
                tone={stressTotal > 0 ? "text-ink-2" : "text-engine"}
              />
            )}
            {!!goals?.regressed && goals.regressed > 0 && (
              <span className="text-caption text-amber">{goals.regressed} regressed</span>
            )}
            {anyLoading && !allLoaded && <span className="text-caption text-ink-3">Checking…</span>}
          </>
        )}
      </div>

      <CollapsibleSection
        title="Goals"
        count={hasGoals ? req.report!.requirements.length : undefined}
        open={open["checks.goals"]}
        onToggle={() => onToggleSection("checks.goals")}
      >
        <GoalsSection
          buildId={buildId}
          hasParams={hasParams}
          report={req.report}
          loading={req.loading}
          setRequirements={req.setRequirements}
        />
      </CollapsibleSection>

      <CollapsibleSection
        title="Manufacturability"
        count={dfmTotal || undefined}
        open={open["checks.dfm"]}
        onToggle={() => onToggleSection("checks.dfm")}
        action={<RerunAction loading={dfm.loading} onRun={dfm.refresh} />}
      >
        <DfmSection state={dfm} selectedId={selectedId} onSelectPart={onSelectPart} />
      </CollapsibleSection>

      <CollapsibleSection
        title="Stress"
        count={stressTotal || undefined}
        open={open["checks.stress"]}
        onToggle={() => onToggleSection("checks.stress")}
        action={<RerunAction loading={stress.loading} onRun={stress.refresh} />}
      >
        <StressSection state={stress} selectedId={selectedId} onSelectPart={onSelectPart} />
      </CollapsibleSection>

      <CollapsibleSection
        title="Fit check"
        open={open["checks.fit"]}
        onToggle={() => onToggleSection("checks.fit")}
      >
        <FitCheckSection />
      </CollapsibleSection>
    </div>
  );
}
