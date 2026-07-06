import { useCallback, useEffect, useRef } from "react";

import { engineSetParams, onEngineStatus } from "../lib/ipc";
import { createParamCommitScheduler } from "../lib/paramCommit";

/**
 * Returns a stable `commit(key, value)` that drives `engine_set_params`
 * single-flight / latest-wins: never more than one rebuild in flight; values
 * arriving mid-build are coalesced to the newest per key. After each rebuild RPC
 * resolves (artifacts are on disk by then), `refresh` re-reads the manifest + GLB
 * so the viewport follows the build directly — not relying on a `model-updated`
 * event.
 *
 * Engine-not-ready recovery (silent): `engineSetParams` returns `null` when the
 * engine can't accept the edit yet — it's still starting, or `engine-status` has
 * reported `ready` but the RPC socket isn't bound for another moment. `send`
 * throws on `null` so the scheduler re-queues the value instead of dropping it,
 * then it's retried automatically until it lands. There is deliberately NO UI
 * message: engine readiness is the header status pill's job, and a second,
 * derived indicator in the sidebar could only contradict it (and would alarm the
 * user right after they made a change). Retries are bounded so a genuinely-down
 * engine never loops.
 */
export function useParamCommit(
  refresh: () => Promise<void>,
  onBuilding?: (building: boolean) => void,
): (key: string, value: number) => void {
  // Keep the latest refresh in a ref so the once-created scheduler always calls
  // the current one (refresh has stable identity today, but this is robust).
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;

  const scheduler = useRef<ReturnType<typeof createParamCommitScheduler> | null>(null);

  // Bounded retry burst for a value held by a failed commit. A burst is a fixed
  // set of spaced retries that does NOT re-arm from its own failures, so a
  // persistently-unavailable engine retries for a few seconds and then stops
  // (the next user edit, or the engine-ready backstop below, starts a fresh one).
  const burstActive = useRef(false);
  const burstTimers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const armRetryBurst = useCallback(() => {
    if (burstActive.current) return; // already retrying; don't stack/loop
    burstActive.current = true;
    burstTimers.current = [400, 1000, 2200, 4000].map((d) =>
      setTimeout(() => scheduler.current?.retry(), d),
    );
    burstTimers.current.push(setTimeout(() => (burstActive.current = false), 4500));
  }, []);

  if (scheduler.current === null) {
    scheduler.current = createParamCommitScheduler({
      send: async (values) => {
        const res = await engineSetParams(values);
        // null = the engine couldn't accept it (it swallows the real error).
        // Throw so the scheduler re-queues instead of treating it as applied.
        if (res === null) throw new Error("engine not ready");
        // Artifacts are on disk by the time the RPC resolves — pull them in now.
        await refreshRef.current();
        return res;
      },
      onError: () => armRetryBurst(),
      onBuildingChange: onBuilding,
    });
  }

  // Backstop for a startup longer than a burst: re-send held edits when the
  // engine transitions to ready (a no-op if nothing is pending).
  useEffect(() => {
    let cancelled = false;
    let unlisten: (() => void) | undefined;
    onEngineStatus((s) => {
      if (!cancelled && s.status === "ready") scheduler.current?.retry();
    })
      .then((fn) => {
        if (cancelled) fn();
        else unlisten = fn;
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      unlisten?.();
      burstTimers.current.forEach(clearTimeout);
    };
  }, []);

  return useCallback((key: string, value: number) => {
    scheduler.current!.commit(key, value);
  }, []);
}
