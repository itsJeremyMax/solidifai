/**
 * FitCheckSection — a quick ISO-286 hole/shaft fit calculator (the agent can
 * run arbitrary tolerance chains; this covers the common mating-pair case).
 */
import { useEffect, useMemo, useState } from "react";

import Select from "../ui/Select";
import { engineToleranceStack } from "../../lib/ipc/engine";
import { parseToleranceResult, type FitType, type ToleranceResult } from "../../lib/validation";

const fmt = (n: number, d = 1) =>
  n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });

const HOLE_FITS = ["H7", "H8", "H9", "H11"];
const SHAFT_FITS = ["g6", "h6", "h7", "f7", "k6", "p6"];

const FIT_TONE: Record<FitType, string> = {
  clearance: "text-engine",
  transition: "text-amber",
  interference: "text-danger",
};

function FitSelect({
  value,
  options,
  onChange,
  label,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
  label: string;
}) {
  return (
    <div className="flex flex-1 flex-col gap-1">
      <span className="text-micro font-bold uppercase tracking-eyebrow text-ink-3">{label}</span>
      <Select
        value={value}
        onChange={onChange}
        ariaLabel={label}
        options={options.map((o) => ({ value: o, label: o }))}
      />
    </div>
  );
}

export default function FitCheckSection() {
  const [nominal, setNominal] = useState(10);
  const [hole, setHole] = useState("H7");
  const [shaft, setShaft] = useState("g6");
  const [result, setResult] = useState<ToleranceResult | null>(null);

  const chain = useMemo(
    () => [
      { label: "hole", nominal, fit: hole, direction: 1 },
      { label: "shaft", nominal, fit: shaft, direction: -1 },
    ],
    [nominal, hole, shaft],
  );

  useEffect(() => {
    let live = true;
    if (!Number.isFinite(nominal) || nominal <= 0) {
      setResult(null);
      return;
    }
    void engineToleranceStack(chain).then((raw) => {
      if (live) setResult(raw ? parseToleranceResult(raw) : null);
    });
    return () => {
      live = false;
    };
  }, [chain, nominal]);

  const fit = result?.fit;

  return (
    <div className="px-3.5 pb-3 pt-1">
      <div className="flex items-end gap-2">
        <label className="flex w-16 flex-col gap-1">
          <span className="text-micro font-bold uppercase tracking-eyebrow text-ink-3">Ø mm</span>
          <input
            type="number"
            min={0.1}
            step={0.5}
            value={nominal}
            onChange={(e) => setNominal(parseFloat(e.target.value))}
            className="h-8.5 w-full rounded-lg border border-line-2 bg-surface px-2.75 font-mono text-caption text-ink transition-colors duration-150 hover:border-line-3 focus:border-accent-line focus:outline-none"
          />
        </label>
        <FitSelect label="Hole" value={hole} options={HOLE_FITS} onChange={setHole} />
        <FitSelect label="Shaft" value={shaft} options={SHAFT_FITS} onChange={setShaft} />
      </div>
      {fit ? (
        <div className="mt-2.5 flex items-center justify-between rounded-md bg-surface-2 px-2.5 py-1.5">
          <span className={`text-caption font-semibold capitalize ${FIT_TONE[fit.type]}`}>
            {fit.type}
          </span>
          <span className="font-mono text-caption tabular-nums text-ink-2">
            gap {fmt(fit.minGap, 3)} … {fmt(fit.maxGap, 3)} mm
          </span>
        </div>
      ) : (
        <p className="mt-2.5 text-caption text-ink-3">
          Pick a hole and shaft fit to check clearance.
        </p>
      )}
    </div>
  );
}
