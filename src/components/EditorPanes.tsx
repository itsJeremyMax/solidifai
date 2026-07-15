import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Viewport, { type ViewportHandle } from "./Viewport";
import ErrorBoundary from "./ErrorBoundary";
import Inspector from "./Inspector";
import type { InteractionTab } from "./InteractionPanel";
import { useArtifacts } from "../hooks/useArtifacts";
import { useHistoryKeys } from "../hooks/useHistoryKeys";
import { appearanceFor } from "../lib/materialAppearance";
import { setPartMaterial } from "../lib/ipc/engine";
import { workspaceHasModel } from "../lib/ipc/workspace";
import { storeWorkspaceThumbnail } from "../lib/workspaces";
import type { Material } from "../lib/materials";
import type { Appearance } from "../lib/artifacts";
import { readEditorView, writeEditorView } from "../state/editorViewState";

/**
 * EditorPanes — the focused-only half of the editor: the live-artifacts
 * subscription ({@link useArtifacts}) plus the 3D viewport and the inspector.
 *
 * Mounted ONLY when its session is active (= the focused workspace, on the editor
 * index route). Receives `wsPath` and passes it directly to `useArtifacts` so
 * artifact reads always target this session's workspace path — not the backend's
 * current focus — eliminating the wrong-workspace viewport race on tab switch.
 *
 * Owns the single live-artifacts subscription and threads the resulting
 * `model` / `glbBytes` / `buildId` to the viewport (3D scene) and `model` to the
 * inspector (tree / params / dims). One subscription + one GLB fetch feed both.
 */
export default function EditorPanes({
  activeTab,
  wsPath,
}: {
  activeTab: InteractionTab;
  wsPath: string;
}) {
  // Seed each persisted piece of state from the module-level view-state cache so
  // tab-switch remounts restore inspector position + selection instantly.
  const [inspectorCollapsed, setInspectorCollapsed] = useState(
    () => readEditorView(wsPath)?.inspectorCollapsed ?? true,
  );
  const [building, setBuilding] = useState(false);

  // null = still checking; true = model.py exists; false = no model.py yet.
  const [hasModelFile, setHasModelFile] = useState<boolean | null>(null);
  useEffect(() => {
    let live = true;
    setHasModelFile(null);
    workspaceHasModel(wsPath)
      .then((v) => {
        if (live) setHasModelFile(v);
      })
      .catch(() => {
        if (live) setHasModelFile(false);
      });
    return () => {
      live = false;
    };
  }, [wsPath]);

  const artifacts = useArtifacts(wsPath);

  // Reveal the Inspector the first time a model exists — covers both the first
  // successful build and reopening a workspace that already has one (artifacts
  // always start null and load model.json after mount, so both produce the same
  // null → present transition). Seeded from cache: if the user already revealed
  // (or manually collapsed) in a previous mount, the latch is already true and
  // the effect won't re-expand the panel.
  const hasModel = artifacts.model != null;
  const revealed = useRef(readEditorView(wsPath)?.revealed ?? false);
  useEffect(() => {
    if (hasModel && !revealed.current) {
      revealed.current = true;
      setInspectorCollapsed(false);
    }
  }, [hasModel]);

  // Thumbnail capture: snapshot the viewport's normalized iso render and persist
  // it for the launcher card. Best-effort everywhere — a failed/empty capture just
  // leaves the existing/placeholder thumbnail and never blocks render. Because the
  // capture frames a canonical iso view (not the live camera), capturing after each
  // build keeps the cached thumbnail current without a separate on-leave snapshot.
  const viewportRef = useRef<ViewportHandle>(null);
  const partCount = (artifacts.model?.objects ?? []).length;
  const captureNow = useCallback(async () => {
    try {
      const blob = await viewportRef.current?.captureThumbnail();
      if (!blob) return;
      const buf = new Uint8Array(await blob.arrayBuffer());
      void storeWorkspaceThumbnail(wsPath, buf, partCount);
    } catch {
      // best-effort: a failed capture leaves the existing/placeholder thumbnail
    }
  }, [wsPath, partCount]);

  // After build: capture (debounced) when a new model is present. The debounce
  // coalesces a burst of edits into one capture; the cleanup cancels a pending
  // capture if a newer build arrives (or the session is backgrounded) first.
  useEffect(() => {
    if (!hasModel) return;
    const t = window.setTimeout(() => void captureNow(), 800);
    return () => window.clearTimeout(t);
  }, [artifacts.publicationId, hasModel, captureNow]);

  // Selection + per-part visibility (session state; pruned when the object set
  // changes). Read by the viewport (apply to the scene) and the inspector
  // (drive the parts list + eye toggles).
  const [selectedId, setSelectedId] = useState<string | null>(
    () => readEditorView(wsPath)?.selectedId ?? null,
  );
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(
    () => new Set(readEditorView(wsPath)?.hiddenIds ?? []),
  );

  // Exploded-view factor (0..100). A pure viewport transform — never sent to the
  // engine, which always builds assembled. Resets when the object set changes.
  const [explode, setExplode] = useState(() => readEditorView(wsPath)?.explode ?? 0);

  // Optimistic per-part material overrides (partId -> chosen Material). The
  // viewport recolors instantly from these; setPartMaterial persists them in the
  // background so mass/exports stay correct. Pruned when the object set changes.
  const [materialOverrides, setMaterialOverrides] = useState<Record<string, Material>>(
    () => readEditorView(wsPath)?.materialOverrides ?? {},
  );

  // Write the whole snapshot back whenever any persisted field changes so a
  // remount (tab switch back to this workspace) restores exactly the last state.
  useEffect(() => {
    writeEditorView(wsPath, {
      inspectorCollapsed,
      revealed: revealed.current,
      selectedId,
      hiddenIds: [...hiddenIds],
      explode,
      materialOverrides,
    });
  }, [wsPath, inspectorCollapsed, selectedId, hiddenIds, explode, materialOverrides]);

  const setPartMaterialOptimistic = useCallback((partId: string, material: Material | null) => {
    setMaterialOverrides((prev) => {
      const next = { ...prev };
      if (material) next[partId] = material;
      else delete next[partId];
      return next;
    });
    // Persist in the background; revert this part on failure (ipc returns null).
    void setPartMaterial(partId, material?.id ?? null).then((res) => {
      if (res === null) {
        setMaterialOverrides((prev) => {
          const next = { ...prev };
          delete next[partId];
          return next;
        });
      }
    });
  }, []);

  const overrideAppearances = useMemo(() => {
    const out: Record<string, Appearance> = {};
    for (const [id, m] of Object.entries(materialOverrides)) {
      out[id] = { material: m.id, ...appearanceFor(m) };
    }
    return out;
  }, [materialOverrides]);

  // Each rebuild yields a fresh `model`. Drop hidden ids whose object is gone and
  // clear the selection if its object disappeared. Param edits keep ids, so the
  // hidden set survives them; undo/redo/goto that changes objects prunes it.
  useEffect(() => {
    const ids = new Set((artifacts.model?.objects ?? []).map((o) => o.id));
    setHiddenIds((prev) => new Set([...prev].filter((id) => ids.has(id))));
    setSelectedId((prev) => (prev && ids.has(prev) ? prev : null));
    setExplode((e) => (ids.size > 1 ? e : 0));
    setMaterialOverrides((prev) => {
      const next: Record<string, Material> = {};
      for (const [id, m] of Object.entries(prev)) if (ids.has(id)) next[id] = m;
      return next;
    });
  }, [artifacts.model]);

  const toggleVisible = useCallback((id: string) => {
    setHiddenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    setHiddenIds((prev) => {
      const objs = artifacts.model?.objects ?? [];
      const anyHidden = objs.some((o) => prev.has(o.id));
      return anyHidden ? new Set() : new Set(objs.map((o) => o.id));
    });
  }, [artifacts.model]);

  // History keys act on the focused model, so binding them here (active-only) is
  // correct — only the focused session listens for ⌘Z / ⇧⌘Z.
  useHistoryKeys();

  // Loading until: we haven't checked model.py yet, OR a model exists but its
  // manifest + mesh haven't both loaded into the viewport yet. Waiting for glbBytes
  // (not just the manifest) means the scene reveals complete (grid + mesh +
  // restored materials) instead of popping in stages.
  const loading =
    hasModelFile === null ||
    (hasModelFile === true && (artifacts.model == null || artifacts.glbBytes == null));

  return (
    <>
      <ErrorBoundary label="viewport">
        <Viewport
          ref={viewportRef}
          model={artifacts.model}
          glbBytes={artifacts.glbBytes}
          buildId={artifacts.buildId}
          activeTab={activeTab}
          selectedId={selectedId}
          hiddenIds={hiddenIds}
          explode={explode}
          onExplodeChange={setExplode}
          partCount={partCount}
          materialOverrides={overrideAppearances}
          building={building}
          loading={loading}
        />
      </ErrorBoundary>
      <Inspector
        model={artifacts.model}
        wsPath={wsPath}
        onRefresh={artifacts.refresh}
        collapsed={inspectorCollapsed}
        onToggle={() => setInspectorCollapsed((c) => !c)}
        selectedId={selectedId}
        hiddenIds={hiddenIds}
        onSelect={setSelectedId}
        onToggleVisible={toggleVisible}
        onToggleAll={toggleAll}
        materialOverrides={materialOverrides}
        onSetPartMaterial={setPartMaterialOptimistic}
        onBuilding={setBuilding}
      />
    </>
  );
}
