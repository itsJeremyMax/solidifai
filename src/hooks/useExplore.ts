/**
 * useExplore — imperative sweep/optimize over a parametric model. Unlike the
 * read-only analysis hooks this isn't tied to buildId: sweeps run only when the
 * user asks (a sweep rebuilds N variants), so it exposes actions, not an effect.
 */
import { useCallback, useState } from "react";

import { engineOptimize, engineSweep } from "../lib/ipc";
import {
  parseOptimizeResult,
  parseSweepReport,
  type Objective,
  type OptimizeResult,
  type SweepReport,
} from "../lib/explore";

export interface ExploreState {
  sweep: SweepReport | null;
  optimum: OptimizeResult | null;
  loading: boolean;
  error: string | null;
  runSweep: (param: string, values?: number[]) => Promise<void>;
  runOptimize: (
    param: string,
    objective: Objective,
    constraints?: Record<string, unknown>,
  ) => Promise<void>;
  reset: () => void;
}

export function useExplore(): ExploreState {
  const [sweep, setSweep] = useState<SweepReport | null>(null);
  const [optimum, setOptimum] = useState<OptimizeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSweep = useCallback(async (param: string, values?: number[]) => {
    setLoading(true);
    setError(null);
    setOptimum(null);
    const raw = await engineSweep(param, values ?? []);
    const parsed = raw ? parseSweepReport(raw) : null;
    if (parsed) setSweep(parsed);
    else setError("Couldn't sweep that parameter just now.");
    setLoading(false);
  }, []);

  const runOptimize = useCallback(
    async (param: string, objective: Objective, constraints?: Record<string, unknown>) => {
      setLoading(true);
      setError(null);
      const raw = await engineOptimize(param, objective, 9, constraints);
      const parsed = raw ? parseOptimizeResult(raw) : null;
      if (parsed) {
        setOptimum(parsed);
        setSweep({ ok: true, param, unit: null, variants: parsed.evaluated });
      } else {
        setError("Couldn't optimize that parameter just now.");
      }
      setLoading(false);
    },
    [],
  );

  const reset = useCallback(() => {
    setSweep(null);
    setOptimum(null);
    setError(null);
  }, []);

  return { sweep, optimum, loading, error, runSweep, runOptimize, reset };
}
