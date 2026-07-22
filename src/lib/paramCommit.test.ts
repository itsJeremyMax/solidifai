/**
 * Tests for the single-flight / latest-wins parameter commit scheduler.
 *
 * These encode the exact property the previous fire-and-forget debounce
 * violated: a hesitant drag (a burst of commits while a slow engine build is in
 * flight) used to enqueue a backlog of full rebuilds that drained AFTER the user
 * stopped (the "huge delay") and stepped the model through stale intermediate
 * values (the "doesn't honor the setting" symptom). The scheduler must instead
 * keep at most ONE build in flight and coalesce everything else to the latest.
 */
import { test, expect } from "vitest";

import { createParamCommitScheduler } from "./paramCommit";

/** A promise whose resolution we control from the outside. */
function deferred<T = void>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Let pending microtasks (the scheduler's .then/.finally chain) settle. */
const tick = () => new Promise<void>((r) => setImmediate(r));

test("idle commit fires a build immediately with that value", async () => {
  const sends: Array<Record<string, number>> = [];
  const gates: Array<ReturnType<typeof deferred>> = [];
  const s = createParamCommitScheduler({
    send: (values) => {
      sends.push({ ...values });
      const d = deferred();
      gates.push(d);
      return d.promise;
    },
  });

  s.commit("explode", 1);
  await tick();

  expect(sends.length).toBe(1);
  expect(sends[0]).toEqual({ explode: 1 });
  expect(s.isInFlight()).toBe(true);
});

test("single-flight: a burst during a slow build coalesces to ONE follow-up with the latest value", async () => {
  const sends: Array<Record<string, number>> = [];
  const gates: Array<ReturnType<typeof deferred>> = [];
  const s = createParamCommitScheduler({
    send: (values) => {
      sends.push({ ...values });
      const d = deferred();
      gates.push(d);
      return d.promise;
    },
  });

  // First movement -> build #1 starts immediately.
  s.commit("explode", 1);
  await tick();
  expect(sends.length, "first commit fires one build").toBe(1);

  // Hesitant drag while build #1 is still running: NO backlog must form.
  for (const v of [5, 12, 30, 47, 88, 100]) s.commit("explode", v);
  await tick();
  expect(sends.length, "no new build is issued while one is in flight").toBe(1);

  // Build #1 finishes -> exactly ONE follow-up with the LATEST value (100),
  // every intermediate value (5,12,30,47,88) is discarded, not replayed.
  gates[0].resolve(undefined);
  await tick();
  expect(sends.length, "exactly one follow-up after the build settles").toBe(2);
  expect(sends[1], "follow-up carries the latest value only").toEqual({ explode: 100 });

  // Nothing left pending -> no further builds, gate is released.
  gates[1].resolve(undefined);
  await tick();
  expect(sends.length).toBe(2);
  expect(s.isInFlight()).toBe(false);
});

test("latest-wins merges the newest value per key across a multi-param burst", async () => {
  const sends: Array<Record<string, number>> = [];
  const gates: Array<ReturnType<typeof deferred>> = [];
  const s = createParamCommitScheduler({
    send: (values) => {
      sends.push({ ...values });
      const d = deferred();
      gates.push(d);
      return d.promise;
    },
  });

  s.commit("explode", 10); // fires build #1
  await tick();
  // While #1 builds, several params change repeatedly.
  s.commit("explode", 20);
  s.commit("wall", 2);
  s.commit("explode", 35);
  s.commit("wall", 3);
  await tick();
  expect(sends.length, "still single-flight").toBe(1);

  gates[0].resolve(undefined);
  await tick();
  expect(sends.length).toBe(2);
  expect(sends[1], "follow-up batches the latest value of every changed key").toEqual({
    explode: 35,
    wall: 3,
  });
});

test("a rejected build surfaces the error and re-queues the value; retry() re-sends it", async () => {
  // Models a param dragged while the engine is still starting: the send fails,
  // and the edit must NOT be lost — it is held and re-sent when retry() fires
  // (the caller drives retry() off the engine-ready signal).
  const sends: Array<Record<string, number>> = [];
  const gates: Array<ReturnType<typeof deferred>> = [];
  const errors: unknown[] = [];
  const commitErrors: unknown[] = [];
  let successes = 0;
  const s = createParamCommitScheduler({
    send: (values) => {
      sends.push({ ...values });
      const d = deferred();
      gates.push(d);
      return d.promise;
    },
    onError: (e) => errors.push(e),
    onSuccess: () => {
      successes += 1;
    },
  });

  s.commit("explode", 70, (error) => commitErrors.push(error)); // build #1 — not ready
  await tick();
  expect(sends.length).toBe(1);

  gates[0].reject(new Error("engine not ready")); // build #1 fails
  await tick();
  expect(errors.length, "the failure is surfaced, not swallowed").toBe(1);
  expect(commitErrors.length, "the originating control is notified once").toBe(1);
  expect(sends.length, "a failed send does NOT auto-hammer the engine").toBe(1);
  expect(s.isInFlight(), "gate released after failure").toBe(false);

  // Engine becomes ready → caller calls retry() → the held value is re-sent.
  s.retry();
  await tick();
  expect(sends.length, "retry() re-sends the held value").toBe(2);
  expect(sends[1], "the dragged value survived the failure").toEqual({ explode: 70 });

  gates[1].resolve(undefined);
  await tick();
  expect(successes, "onSuccess fires once the engine accepts the build").toBe(1);
});

test("a newer commit during an in-flight build supersedes a failed older value", async () => {
  const sends: Array<Record<string, number>> = [];
  const gates: Array<ReturnType<typeof deferred>> = [];
  const s = createParamCommitScheduler({
    send: (values) => {
      sends.push({ ...values });
      const d = deferred();
      gates.push(d);
      return d.promise;
    },
  });

  s.commit("a", 1); // build #1 (will fail)
  await tick();
  s.commit("a", 2); // newer value queued while #1 in flight

  gates[0].reject(new Error("boom")); // #1 fails — must NOT clobber the newer a=2
  await tick();
  expect(sends.length, "no auto-retry on failure").toBe(1);

  s.retry();
  await tick();
  expect(sends.length).toBe(2);
  expect(sends[1], "the newer value wins, the stale failed one is dropped").toEqual({ a: 2 });
});

test("a prototype-named parameter survives failure requeue and retry", async () => {
  const sends: Array<Record<string, number>> = [];
  const gates: Array<ReturnType<typeof deferred>> = [];
  const s = createParamCommitScheduler({
    send: (values) => {
      sends.push({ ...values });
      const d = deferred();
      gates.push(d);
      return d.promise;
    },
  });

  s.commit("toString", 7);
  await tick();
  gates[0].reject(new Error("engine not ready"));
  await tick();

  s.retry();
  await tick();
  expect(sends).toEqual([{ toString: 7 }, { toString: 7 }]);
});

test("a quiet commit after the build settles still goes out (no lost trailing value)", async () => {
  const sends: Array<Record<string, number>> = [];
  const gates: Array<ReturnType<typeof deferred>> = [];
  const s = createParamCommitScheduler({
    send: (values) => {
      sends.push({ ...values });
      const d = deferred();
      gates.push(d);
      return d.promise;
    },
  });

  s.commit("x", 1); // build #1
  await tick();
  gates[0].resolve(undefined); // build #1 done, pipeline idle
  await tick();
  expect(sends.length).toBe(1);

  s.commit("x", 2); // a fresh, isolated change must fire on its own
  await tick();
  expect(sends.length).toBe(2);
  expect(sends[1]).toEqual({ x: 2 });
});
