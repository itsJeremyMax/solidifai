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

import { onModelUpdated } from "../lib/ipc/status";
import { readModelSnapshot } from "../lib/ipc/workspace";
import { parseModelInfo, type ModelInfo } from "../lib/artifacts";

/** Module-level artifact cache keyed by wsPath — survives EditorPanes unmount/remount
 *  so the viewport shows the last model immediately on tab switch, then refreshes. */
interface ArtifactCacheEntry {
  model: ModelInfo | null;
  glbBytes: Uint8Array | null;
  buildId: number;
  publicationId: string | null;
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
  /** Immutable generation identity; unlike buildId it survives engine restarts. */
  publicationId: string | null;
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
  const [publicationId, setPublicationId] = useState<string | null>(
    () => cached?.publicationId ?? null,
  );

  // Each request gets a strictly increasing epoch, so an older filesystem/IPC
  // completion can never replace the newest publication.
  const refreshEpochRef = useRef(0);
  // Flipped true on unmount so an in-flight refresh doesn't setState after teardown.
  const cancelledRef = useRef<boolean>(false);

  const refresh = useCallback(async (): Promise<void> => {
    const epoch = ++refreshEpochRef.current;
    try {
      const snapshot = await readModelSnapshot(wsPath);
      if (cancelledRef.current || epoch !== refreshEpochRef.current) return;
      if (!snapshot) {
        setModel(null);
        setGlbBytes(null);
        setBuildId(-1);
        setPublicationId(null);
        ARTIFACT_CACHE.delete(wsPath);
        return;
      }
      const info = parseModelInfo(snapshot.manifest);
      if (!info) return;
      const bytes = new Uint8Array(snapshot.glb);
      const nextBuildId = info.buildId;
      const nextPublicationId = snapshot.publicationId;
      setModel(info);
      setGlbBytes(bytes);
      setBuildId(nextBuildId);
      setPublicationId(nextPublicationId);
      ARTIFACT_CACHE.set(wsPath, {
        model: info,
        glbBytes: bytes,
        buildId: nextBuildId,
        publicationId: nextPublicationId,
      });
    } catch {
      // Keep the last coherent pair. A malformed pointer/mirror failure is
      // transient during publication and must not blank a valid viewport.
    }
  }, [wsPath]);

  useEffect(() => {
    cancelledRef.current = false;
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

  return { model, glbBytes, buildId, publicationId, refresh };
}
