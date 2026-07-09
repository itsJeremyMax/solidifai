/**
 * useAssemblyMeta — fetch the engine's `get_assembly_tree` for the current build
 * and shape it into the occurrence families + joints the assembly tree renders.
 *
 * The geometry snapshot (`model.json`) is the source of truth for ids and
 * visibility; this call only enriches it with declared intent (how many times a
 * part is placed, at which frames, mirrors, and the skeleton's joints). It is
 * read-only and cheap (no rebuild), so we fetch whenever the panel is showing an
 * assembly build. Single-model workspaces and engines older than protocol 11
 * degrade to empty metadata (no families, no joints) — the tree renders exactly
 * as it did before.
 */
import { useEffect, useRef, useState } from "react";

import { engineGetAssemblyTree } from "../lib/ipc/engine";
import {
  deriveJoints,
  deriveOccurrenceFamilies,
  parseAssemblyTree,
  type JointInfo,
  type OccurrenceFamily,
} from "../lib/assemblyMeta";

export interface AssemblyMetaState {
  families: Map<string, OccurrenceFamily>;
  joints: JointInfo[];
}

const EMPTY: AssemblyMetaState = { families: new Map(), joints: [] };

// Per-build cache: the tree unmounts and remounts as the Parts section toggles,
// and the metadata never changes within a build, so one fetch per build is
// plenty. buildId is monotonic.
const CACHE = new Map<number, AssemblyMetaState>();

// Same engine-warmup tolerance as useDfm: a fresh model can be on disk a beat
// before the engine answers RPCs. Retry a null (not-ready / no-reply) reply
// quietly before settling to empty metadata.
const RETRY_DELAYS_MS = [250, 600, 1200];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * @param buildId Current build; `< 0` means no model yet.
 * @param active  Fetch only when the current model is an assembly. When false,
 *                returns empty metadata without calling the engine.
 */
export function useAssemblyMeta(buildId: number, active: boolean): AssemblyMetaState {
  const [state, setState] = useState<AssemblyMetaState>(() => CACHE.get(buildId) ?? EMPTY);
  const reqRef = useRef(0);

  useEffect(() => {
    if (!active || buildId < 0) {
      setState(EMPTY);
      return;
    }
    const cached = CACHE.get(buildId);
    if (cached) {
      setState(cached);
      return;
    }
    const token = ++reqRef.current;
    void (async () => {
      for (let attempt = 0; ; attempt++) {
        const raw = await engineGetAssemblyTree();
        if (token !== reqRef.current) return; // superseded by a newer build
        const meta = parseAssemblyTree(raw);
        if (meta) {
          const next: AssemblyMetaState = {
            families: deriveOccurrenceFamilies(meta),
            joints: deriveJoints(meta),
          };
          CACHE.set(buildId, next);
          setState(next);
          return;
        }
        // No usable metadata. A transient null (engine warming up) is worth a
        // couple of retries; a definitive empty settles quietly.
        if (raw !== null || attempt >= RETRY_DELAYS_MS.length) {
          CACHE.set(buildId, EMPTY);
          setState(EMPTY);
          return;
        }
        await sleep(RETRY_DELAYS_MS[attempt]);
        if (token !== reqRef.current) return;
      }
    })();
  }, [active, buildId]);

  return state;
}
