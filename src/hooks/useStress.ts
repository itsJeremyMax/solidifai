/**
 * useStress — lazily fetch the stress hot-spot report for the current build,
 * cached per `buildId`. Pass `active=false` to skip until the Measure tab is
 * open (the edge walk is cheap but still on-demand). Mirrors `useDfm`.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { engineStressCheck } from "../lib/ipc";
import { parseStressReport, type StressReport } from "../lib/validation";

export interface StressState {
  report: StressReport | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

const CACHE = new Map<number, StressReport>();
const RETRY_DELAYS_MS = [300, 600, 1200, 2000];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useStress(buildId: number, active: boolean): StressState {
  const [report, setReport] = useState<StressReport | null>(() => CACHE.get(buildId) ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reqRef = useRef(0);

  const run = useCallback(async () => {
    const cached = CACHE.get(buildId);
    if (cached) {
      setReport(cached);
      setError(null);
      return;
    }
    const token = ++reqRef.current;
    setLoading(true);
    setError(null);
    for (let attempt = 0; ; attempt++) {
      const raw = await engineStressCheck();
      if (token !== reqRef.current) return;
      const parsed = raw ? parseStressReport(raw) : null;
      if (parsed) {
        CACHE.set(buildId, parsed);
        setReport(parsed);
        setError(null);
        setLoading(false);
        return;
      }
      if (attempt >= RETRY_DELAYS_MS.length) {
        setReport(null);
        setError("Couldn't run the stress check just now.");
        setLoading(false);
        return;
      }
      await sleep(RETRY_DELAYS_MS[attempt]);
      if (token !== reqRef.current) return;
    }
  }, [buildId]);

  useEffect(() => {
    if (active && buildId >= 0) void run();
  }, [active, buildId, run]);

  const refresh = useCallback(() => {
    CACHE.delete(buildId);
    void run();
  }, [buildId, run]);

  return { report, loading, error, refresh };
}
