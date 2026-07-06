/**
 * ExploreSection — the Model tab's design-space explorer (only meaningful for a
 * parametric model). Pick a parameter, sweep it across its range for a measured
 * mass/size table, or optimize it toward lightest/heaviest within the current
 * size. Each result applies to the live model with the normal param-commit path.
 */
import { useMemo, useState } from "react";
import { Check, Sparkles } from "lucide-react";

import Select from "../ui/Select";
import { useExplore } from "../../hooks/useExplore";
import type { Objective, SweepVariant } from "../../lib/explore";

export interface ExploreParam {
  key: string;
  min: number;
  max: number;
  step: number;
  unit: string;
}

/** ~6 evenly spaced values across [min, max], snapped to step, de-duplicated. */
function sampleValues(p: ExploreParam): number[] {
  const n = 6;
  const span = p.max - p.min;
  if (span <= 0) return [p.min];
  const step = p.step > 0 ? p.step : span / (n - 1);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const raw = p.min + (span * i) / (n - 1);
    const snapped = Math.round(raw / step) * step;
    const v = Math.round(snapped * 1000) / 1000;
    if (!out.includes(v)) out.push(v);
  }
  return out;
}

const fmt = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });

function VariantRow({
  v,
  unit,
  maxMass,
  isCurrent,
  isBest,
  onApply,
}: {
  v: SweepVariant;
  unit: string | null;
  maxMass: number;
  isCurrent: boolean;
  isBest: boolean;
  onApply: () => void;
}) {
  if (!v.ok) {
    return (
      <div className="flex items-center gap-2 px-3.5 py-1.5 text-caption text-ink-3">
        <span className="font-mono">
          {fmt(v.value)}
          {unit ? ` ${unit}` : ""}
        </span>
        <span className="text-danger">build failed</span>
      </div>
    );
  }
  const pct = maxMass > 0 ? Math.max(4, ((v.mass ?? 0) / maxMass) * 100) : 0;
  return (
    <button
      type="button"
      onClick={onApply}
      title="Apply this value"
      className={
        isBest
          ? "group flex w-full items-center gap-2 bg-accent-tint px-3.5 py-1.5 text-left shadow-[inset_2px_0_0_var(--color-accent)]"
          : "group flex w-full items-center gap-2 px-3.5 py-1.5 text-left transition-colors hover:bg-surface-2"
      }
    >
      <span className="w-14 shrink-0 font-mono text-caption tabular-nums text-ink">
        {fmt(v.value)}
        {unit ? <span className="text-ink-3"> {unit}</span> : null}
      </span>
      <span className="relative h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-line-2">
        <span
          className={`absolute inset-y-0 left-0 rounded-full ${isBest ? "bg-accent" : "bg-ink-3"}`}
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="w-14 shrink-0 text-right font-mono text-caption tabular-nums text-ink-2">
        {fmt(v.mass ?? 0)} g
      </span>
      {isCurrent ? (
        <Check size={12} strokeWidth={2.4} className="shrink-0 text-engine" />
      ) : (
        <span className="w-3 shrink-0" />
      )}
    </button>
  );
}

export default function ExploreSection({
  params,
  currentValues,
  currentSize,
  onApply,
}: {
  params: ExploreParam[];
  currentValues: Record<string, number>;
  currentSize?: [number, number, number];
  onApply: (key: string, value: number) => void;
}) {
  const [param, setParam] = useState(params[0]?.key ?? "");
  const [objective, setObjective] = useState<Objective>("min_mass");
  const [fitsCurrent, setFitsCurrent] = useState(false);
  const { sweep, optimum, loading, error, runSweep, runOptimize } = useExplore();

  const selected = params.find((p) => p.key === param) ?? params[0];

  const maxMass = useMemo(
    () => Math.max(0, ...(sweep?.variants ?? []).map((v) => (v.ok ? (v.mass ?? 0) : 0))),
    [sweep],
  );

  if (params.length === 0) {
    return (
      <p className="px-3.5 pb-2.75 pt-0.5 text-xs text-ink-3">
        This model has no parameters to explore.
      </p>
    );
  }

  const doSweep = () => selected && void runSweep(selected.key, sampleValues(selected));
  const doOptimize = () =>
    selected &&
    void runOptimize(
      selected.key,
      objective,
      fitsCurrent && currentSize ? { max_size: currentSize } : undefined,
    );

  return (
    <div className="pb-2.5">
      {/* controls */}
      <div className="flex items-center gap-1.5 px-3.5 pb-2 pt-0.5">
        <Select
          value={param}
          onChange={setParam}
          ariaLabel="Parameter to explore"
          className="min-w-0 flex-1"
          options={params.map((p) => ({ value: p.key, label: p.key }))}
        />
        <button
          type="button"
          onClick={doSweep}
          disabled={loading}
          className="h-8.5 shrink-0 rounded-lg bg-accent px-3 text-caption font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          Sweep
        </button>
      </div>

      {/* optimize */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 px-3.5 pb-2">
        <Select
          value={objective}
          onChange={(v) => setObjective(v as Objective)}
          ariaLabel="Optimization objective"
          className="w-28"
          options={[
            { value: "min_mass", label: "Lightest" },
            { value: "max_mass", label: "Heaviest" },
          ]}
        />
        {currentSize && (
          <label className="flex items-center gap-1.5 text-caption text-ink-2">
            <input
              type="checkbox"
              checked={fitsCurrent}
              onChange={(e) => setFitsCurrent(e.target.checked)}
              className="h-3.5 w-3.5 accent-accent"
            />
            fits current size
          </label>
        )}
        <button
          type="button"
          onClick={doOptimize}
          disabled={loading}
          className="ml-auto inline-flex h-8.5 shrink-0 items-center gap-1 rounded-lg border border-line-2 bg-surface px-2.75 text-caption font-medium text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink disabled:opacity-50"
        >
          <Sparkles size={12} strokeWidth={2} />
          Optimize
        </button>
      </div>

      {error && <p className="px-3.5 py-1 text-caption text-ink-3">{error}</p>}

      {/* results */}
      {sweep && selected && (
        <div className="border-t border-line pt-1">
          {sweep.variants.map((v) => (
            <VariantRow
              key={v.value}
              v={v}
              unit={sweep.unit ?? selected.unit}
              maxMass={maxMass}
              isCurrent={currentValues[sweep.param] === v.value}
              isBest={optimum?.best?.value === v.value && optimum?.param === sweep.param}
              onApply={() => onApply(sweep.param, v.value)}
            />
          ))}
          {optimum && optimum.best === null && (
            <p className="px-3.5 py-1.5 text-caption text-ink-3">
              No value fits the current size. Loosen the constraint or the size goal.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
