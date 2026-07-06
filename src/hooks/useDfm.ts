/**
 * useDfm — lazily fetch the DFM report for the current build, cached per
 * `buildId` so reopening the panel is instant and switching parts never
 * recomputes. Pass `active=false` to skip fetching until the DFM tab is open:
 * wall-thickness sampling is too costly to run on every build.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { engineAnalyzeDfm } from "../lib/ipc";
import { parseDfmReport, type DfmReport } from "../lib/dfm";

export interface DfmState {
  report: DfmReport | null;
  loading: boolean;
  error: string | null;
  /** Recompute now, bypassing the cache (the Re-run action). */
  refresh: () => void;
}

// Module-level cache keyed by buildId. Lives outside the hook so a report
// survives the DFM tab unmounting (the Inspector renders one tab at a time), so
// reopening the tab for the same build is instant rather than re-running the
// costly wall-thickness sampling. buildId is monotonic; a session never
// accumulates enough builds for this to matter.
const CACHE = new Map<number, DfmReport>();

// Transient-not-ready backoff. The frontend sees a model the moment model.json
// is on disk, but the engine process can still be mid-startup or finishing a
// rebuild and reply "no model" for a beat. That is not a real failure -- it is
// the same engine-readiness window useParamCommit tolerates. So a null/empty
// reply is retried quietly (staying in the loading state) and only surfaced as
// an error if it never resolves.
const RETRY_DELAYS_MS = [300, 600, 1200, 2000];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useDfm(buildId: number, active: boolean): DfmState {
  const [report, setReport] = useState<DfmReport | null>(() => CACHE.get(buildId) ?? null);
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
    // Retry a transient empty reply (engine still warming up) before erroring,
    // staying in the loading state so the panel never flashes a scary message.
    for (let attempt = 0; ; attempt++) {
      const raw = await engineAnalyzeDfm();
      if (token !== reqRef.current) return; // a newer request superseded this one
      const parsed = raw ? parseDfmReport(raw) : null;
      if (parsed) {
        CACHE.set(buildId, parsed);
        setReport(parsed);
        setError(null);
        setLoading(false);
        return;
      }
      if (attempt >= RETRY_DELAYS_MS.length) {
        setReport(null);
        setError("Couldn't analyze the model just now.");
        setLoading(false);
        return;
      }
      await sleep(RETRY_DELAYS_MS[attempt]);
      if (token !== reqRef.current) return; // superseded during the backoff
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
