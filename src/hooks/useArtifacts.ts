/**
 * useArtifacts — owns the live render-artifact state (the parsed `model.json`
 * manifest + the raw GLB bytes) and keeps it in sync with the engine.
 *
 * Refresh is driven two ways, deliberately redundant so a param edit ALWAYS
 * reaches the viewport:
 *   1. Direct (authoritative): callers that mutate the model (param sliders, etc.)
 *      await the engine RPC, then call the returned `refresh()`. The engine writes
 *      its artifacts before it replies, so by the time the RPC resolves the new
 *      model is on disk — re-reading is immediate and never misses.
 *   2. Event (fallback): the `model-updated` event (emitted by the Rust command
 *      layer and the filesystem watcher) also calls `refresh()`, covering
 *      out-of-band edits — the agent/terminal editing the model over MCP, which
 *      never crosses the UI's RPC path.
 *
 * `refresh()` re-reads the manifest and, when the build identity CHANGED, the GLB
 * bytes. Every `invoke`/`listen` is wrapped so a missing/late backend leaves the
 * UI in a clean empty state rather than throwing into render.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { onModelUpdated, readModelGlb, readModelJson } from "../lib/ipc";
import { parseModelInfo, type ModelInfo } from "../lib/artifacts";

/** Module-level artifact cache keyed by wsPath — survives EditorPanes unmount/remount
 *  so the viewport shows the last model immediately on tab switch, then refreshes. */
interface ArtifactCacheEntry {
  model: ModelInfo | null;
  glbBytes: Uint8Array | null;
  buildId: number;
}
const ARTIFACT_CACHE = new Map<string, ArtifactCacheEntry>();
export const clearArtifactCache = (wsPath: string): void => void ARTIFACT_CACHE.delete(wsPath);

/** Live artifact state consumed by the viewport + inspector. */
export interface ArtifactsState {
  /** Parsed render manifest, or null if no valid build is available. */
  model: ModelInfo | null;
  /** Raw GLB bytes for the current build, or null if none loaded yet. */
  glbBytes: Uint8Array | null;
  /** buildId of the GLB currently in `glbBytes` (-1 = none loaded). */
  buildId: number;
  /**
   * Re-read the manifest + (if the build changed) the GLB. Call after a mutation
   * RPC resolves so the viewport reflects the new build without waiting on an
   * event. Stable identity — safe to capture once.
   */
  refresh: () => Promise<void>;
}

export function useArtifacts(wsPath: string): ArtifactsState {
  // Seed from cache so the viewport shows the last model immediately on remount.
  const cached = ARTIFACT_CACHE.get(wsPath);
  const [model, setModel] = useState<ModelInfo | null>(() => cached?.model ?? null);
  const [glbBytes, setGlbBytes] = useState<Uint8Array | null>(() => cached?.glbBytes ?? null);
  const [buildId, setBuildId] = useState<number>(() => cached?.buildId ?? -1);

  // Highest buildId whose GLB we've fetched — guards redundant / out-of-order GLB
  // loads when several refreshes overlap. A ref so the latest value is visible
  // synchronously inside the async body. Seed from cache so we don't re-fetch
  // the GLB when the cached build is still current after a remount.
  const loadedBuildRef = useRef<number>(cached?.buildId ?? -1);
  // Flipped true on unmount so an in-flight refresh doesn't setState after teardown.
  const cancelledRef = useRef<boolean>(false);

  const refresh = useCallback(async (): Promise<void> => {
    // 1. Manifest — always re-read so metadata (dims, mass, params) stays live.
    let info: ModelInfo | null;
    try {
      info = parseModelInfo(await readModelJson(wsPath));
    } catch {
      info = null;
    }
    if (cancelledRef.current) return;
    setModel(info);
    // Keep the cache's model field current; preserve the existing glb/buildId
    // until we have fresh bytes (below) so a concurrent read of the cache is
    // always coherent (model + bytes belonging to the same build or a newer one).
    const prevEntry = ARTIFACT_CACHE.get(wsPath);
    ARTIFACT_CACHE.set(wsPath, {
      model: info,
      glbBytes: prevEntry?.glbBytes ?? null,
      buildId: prevEntry?.buildId ?? -1,
    });

    // Reload the GLB whenever the build identity CHANGES — not only when it
    // increases. The engine's buildId restarts from 1 when the engine process
    // restarts, so a strict "newer only" check would wrongly ignore a fresh model
    // whose id is ≤ one persisted from a previous run (a viewport/inspector
    // desync: metadata updates while the 3D mesh stays stale).
    const nextBuildId = info?.buildId ?? -1;
    if (!Number.isFinite(nextBuildId) || nextBuildId === loadedBuildRef.current) {
      return; // Exact same build already loaded — skip the redundant GLB fetch.
    }

    try {
      const bytes = await readModelGlb(wsPath);
      if (cancelledRef.current) return;
      loadedBuildRef.current = nextBuildId;
      setGlbBytes(bytes);
      setBuildId(nextBuildId);
      ARTIFACT_CACHE.set(wsPath, { model: info, glbBytes: bytes, buildId: nextBuildId });
    } catch {
      // GLB not present yet (e.g. json landed first) — manifest still applied.
    }
  }, [wsPath]);

  useEffect(() => {
    cancelledRef.current = false;
    // loadedBuildRef is already seeded from the cache (or -1 for a cold start) —
    // no reset needed. Each EditorPanes mount is a fresh component instance with a
    // fresh useRef, so there is no stale value to clear here.

    // Initial load: pull whatever build already exists.
    void refresh();

    // Fallback path: out-of-band builds (agent/terminal over MCP) still refresh.
    let unlisten: (() => void) | undefined;
    onModelUpdated(() => {
      void refresh();
    })
      .then((fn) => {
        if (cancelledRef.current) fn();
        else unlisten = fn;
      })
      .catch(() => {
        // Backend not available — initial empty state stands.
      });

    return () => {
      cancelledRef.current = true;
      unlisten?.();
    };
  }, [wsPath, refresh]);

  return { model, glbBytes, buildId, refresh };
}
