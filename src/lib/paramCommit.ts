/**
 * Single-flight, latest-wins scheduler for parameter commits.
 *
 * Every parameter change asks the engine for a full rebuild (set_params →
 * build(**values) → render), and the engine serializes builds under a lock. The
 * previous pipeline fired each commit fire-and-forget behind a trailing
 * debounce, so a hesitant "dial-it-in" drag (each pause past the debounce fired
 * another commit) enqueued a BACKLOG of rebuilds that the engine drained long
 * after the user let go — the model lagged seconds behind (the "huge delay") and
 * stepped through stale intermediate values (it "didn't honor" the value you
 * actually picked).
 *
 * This scheduler removes the backlog by construction:
 *  - At most ONE engine call is in flight at any time (single-flight).
 *  - While that call runs, further commits only update the pending payload —
 *    the latest value per key wins; intermediate values are coalesced away,
 *    never queued.
 *  - When the in-flight call settles, if anything changed meanwhile exactly one
 *    follow-up call fires carrying the latest values.
 *
 * Net effect during a drag: the engine is always working toward the user's
 * CURRENT target and never more than one step behind it; on release it converges
 * in at most one extra build. It is framework-free and deterministic (no timers)
 * so it can be unit-tested directly — see paramCommit.test.ts.
 *
 * Failure handling: a `send` can fail because the engine is still starting (its
 * RPC socket isn't registered yet) — historically that failure was swallowed and
 * the edit was LOST, so a param dragged during engine startup did nothing. The
 * scheduler now RE-QUEUES a failed value (unless a newer commit superseded it)
 * and does NOT auto-retry (no hammering a down engine). A `retry()` — driven by
 * the caller when the engine becomes ready, or by the next user commit — re-sends
 * it, so the edit lands as soon as the engine is up.
 */

/** A batch of parameter values keyed by parameter name. */
export type ParamValue = number | boolean | string;
export type ParamValues = Record<string, ParamValue>;
export type ParamCommitErrorHandler = (error: unknown) => void;

export interface ParamCommitOptions {
  /**
   * Perform the engine round-trip for a batch of values. Resolves on a build the
   * engine accepted; REJECTS (or throws) when the engine couldn't apply it (e.g.
   * not ready) so the scheduler can re-queue and retry rather than drop the edit.
   */
  send: (values: ParamValues) => Promise<unknown>;
  /** Called when a `send` fails — surface "engine not ready" instead of silence. */
  onError?: (error: unknown) => void;
  /** Called after a `send` succeeds — clear any "not ready" notice. */
  onSuccess?: () => void;
  /** Called when the in-flight state changes (drives a "Building" indicator). */
  onBuildingChange?: (building: boolean) => void;
}

export interface ParamCommitScheduler {
  /** Record the latest value for `key` and schedule a send (single-flight). */
  commit: (key: string, value: ParamValue, onError?: ParamCommitErrorHandler) => void;
  /** Re-send any value left pending by a prior failure (e.g. once engine ready). */
  retry: () => void;
  /** True while an engine call is outstanding (used by tests/diagnostics). */
  isInFlight: () => boolean;
}

export function createParamCommitScheduler(options: ParamCommitOptions): ParamCommitScheduler {
  const { send, onError, onSuccess, onBuildingChange } = options;

  let pending: ParamValues = Object.create(null);
  let pendingErrorHandlers: ParamCommitErrorHandler[] = [];
  let hasPending = false;
  let inFlight = false;

  const flush = (): void => {
    // Single-flight gate: never overlap engine builds, and never send nothing.
    if (inFlight || !hasPending) return;

    const payload = pending;
    const errorHandlers = pendingErrorHandlers;
    pending = Object.create(null);
    pendingErrorHandlers = [];
    hasPending = false;
    inFlight = true;
    onBuildingChange?.(true);

    // Promise.resolve().then(send) so a synchronous throw inside `send` becomes a
    // rejection handled below, and the in-flight flag is always cleared.
    Promise.resolve()
      .then(() => send(payload))
      .then(
        () => {
          inFlight = false;
          onBuildingChange?.(false);
          onSuccess?.();
          // A newer value may have arrived mid-build — fire exactly one follow-up.
          flush();
        },
        (error: unknown) => {
          onError?.(error);
          // Re-queue the failed values UNLESS a newer commit already superseded
          // them, so the edit isn't lost. Don't auto-flush: that would hammer a
          // still-down engine. `retry()` (engine-ready) or the next commit re-sends.
          for (const key of Object.keys(payload)) {
            if (!Object.prototype.hasOwnProperty.call(pending, key)) pending[key] = payload[key];
          }
          hasPending = Object.keys(pending).length > 0;
          inFlight = false;
          onBuildingChange?.(false);
          for (const handler of errorHandlers) {
            try {
              handler(error);
            } catch {
              // A view callback cannot compromise scheduler recovery or retries.
            }
          }
        },
      );
  };

  return {
    commit(key, value, commitOnError) {
      pending[key] = value;
      if (commitOnError) pendingErrorHandlers.push(commitOnError);
      hasPending = true;
      flush();
    },
    retry() {
      flush();
    },
    isInFlight() {
      return inFlight;
    },
  };
}
