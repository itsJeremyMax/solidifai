/**
 * useMeasure — lazily fetch mass properties for the current build, cached per
 * `buildId` so reopening the Measure tab is instant and switching parts never
 * recomputes. Pass `active=false` to skip fetching until the tab is open.
 * Mirrors `useDfm`.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { engineMeasure } from "../lib/ipc/engine";
import { parseMeasureReport, type MeasureReport } from "../lib/validation";

export interface MeasureState {
  report: MeasureReport | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

const CACHE = new Map<number, MeasureReport>();
const RETRY_DELAYS_MS = [300, 600, 1200, 2000];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useMeasure(buildId: number, active: boolean): MeasureState {
  const [report, setReport] = useState<MeasureReport | null>(() => CACHE.get(buildId) ?? null);
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
      const raw = await engineMeasure();
      if (token !== reqRef.current) return;
      const parsed = raw ? parseMeasureReport(raw) : null;
      if (parsed) {
        CACHE.set(buildId, parsed);
        setReport(parsed);
        setError(null);
        setLoading(false);
        return;
      }
      if (attempt >= RETRY_DELAYS_MS.length) {
        setReport(null);
        setError("Couldn't measure the model just now.");
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
