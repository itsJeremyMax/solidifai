/**
 * useConverge — drive the engine's `converge_to_spec` routine from UI.
 *
 * Non-destructive: the engine searches its declared PARAMS for values that
 * satisfy all predicate requirements, without rebuilding the live model unless
 * `apply` is set to true. Exposes `run`, `result`, `loading`, and `clear`.
 */
import { useCallback, useState } from "react";

import { engineConvergeToSpec } from "../lib/ipc";
import { parseConvergeResult, type ConvergeResult } from "../lib/requirements";

export interface ConvergeState {
  /** Trigger a convergence search. Pass apply=true to commit found params. */
  run: (opts?: { objective?: string; apply?: boolean }) => Promise<void>;
  result: ConvergeResult | null;
  loading: boolean;
  error: string | null;
  clear: () => void;
}

export function useConverge(buildId: number): ConvergeState {
  // buildId is the caller's build reference; results auto-clear when the panel
  // re-mounts for a new build, which is why we carry it in the signature.
  void buildId;
  const [result, setResult] = useState<ConvergeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (opts: { objective?: string; apply?: boolean } = {}) => {
    setLoading(true);
    setError(null);
    setResult(null);
    const raw = await engineConvergeToSpec(opts.objective ?? "min_mass", opts.apply ?? false);
    if (raw) {
      const parsed = parseConvergeResult(raw);
      if (parsed) {
        setResult(parsed);
      } else {
        setError("Unexpected response from the engine.");
      }
    } else {
      setError("Engine is not ready. Try again in a moment.");
    }
    setLoading(false);
  }, []);

  const clear = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  return { run, result, loading, error, clear };
}
