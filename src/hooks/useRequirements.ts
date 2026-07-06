/**
 * useRequirements — evaluate the workspace's design requirements for the current
 * build, cached per buildId (re-checks when the model rebuilds). Unlike the
 * read-only checks, requirements are editable: `setRequirements` persists a new
 * set, invalidates the current build's cache, and re-evaluates.
 *
 * Result rows carry `delta` (regression tracking) and the summary carries
 * `regressed`/`fixed` when the engine returns them.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { engineCheckRequirements, engineSetRequirements } from "../lib/ipc";
import {
  parseRequirementsReport,
  type Requirement,
  type RequirementsReport,
} from "../lib/requirements";

export interface RequirementsState {
  report: RequirementsReport | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
  /** Persist a new requirement set and re-evaluate it against this build. */
  setRequirements: (reqs: Requirement[]) => Promise<void>;
}

const CACHE = new Map<number, RequirementsReport>();
const RETRY_DELAYS_MS = [300, 600, 1200, 2000];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useRequirements(buildId: number, active: boolean): RequirementsState {
  const [report, setReport] = useState<RequirementsReport | null>(() => CACHE.get(buildId) ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reqRef = useRef(0);

  const run = useCallback(
    async (bypassCache = false) => {
      if (!bypassCache) {
        const cached = CACHE.get(buildId);
        if (cached) {
          setReport(cached);
          setError(null);
          return;
        }
      }
      const token = ++reqRef.current;
      setLoading(true);
      setError(null);
      for (let attempt = 0; ; attempt++) {
        const raw = await engineCheckRequirements();
        if (token !== reqRef.current) return;
        const parsed = raw ? parseRequirementsReport(raw) : null;
        if (parsed) {
          CACHE.set(buildId, parsed);
          setReport(parsed);
          setError(null);
          setLoading(false);
          return;
        }
        if (attempt >= RETRY_DELAYS_MS.length) {
          setError("Couldn't check requirements just now.");
          setLoading(false);
          return;
        }
        await sleep(RETRY_DELAYS_MS[attempt]);
        if (token !== reqRef.current) return;
      }
    },
    [buildId],
  );

  useEffect(() => {
    if (active && buildId >= 0) void run();
  }, [active, buildId, run]);

  const refresh = useCallback(() => {
    CACHE.delete(buildId);
    void run(true);
  }, [buildId, run]);

  const setRequirements = useCallback(
    async (reqs: Requirement[]) => {
      await engineSetRequirements(reqs);
      CACHE.delete(buildId);
      await run(true);
    },
    [buildId, run],
  );

  return { report, loading, error, refresh, setRequirements };
}
