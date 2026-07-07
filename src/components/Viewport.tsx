/**
 * Viewport — center pane. A live three.js scene on the graphite radial stage,
 * with the floating tool dock (orbit / pan / measure / fit) and the bottom-left
 * HUD (nav gizmo + dimensions · mass).
 *
 * The GLB streamed from the engine is loaded by {@link useThreeScene}; the
 * manifest (`model`) drives the HUD readouts (bbox + mass). Both arrive as props
 * from {@link AppShell}, which owns the single `useArtifacts` subscription, so the
 * viewport and the inspector always reflect the same live build. The graphite
 * gradient lives in CSS behind a transparent WebGL canvas so it stays exactly
 * on-brand with the original placeholder.
 */
import { forwardRef, memo, useEffect, useImperativeHandle, useRef, useState } from "react";
import {
  Box,
  Loader2,
  Maximize,
  Move,
  RotateCw,
  Rotate3d,
  Ruler,
  TriangleAlert,
  Upload,
} from "lucide-react";

import type { ArtifactsState } from "../hooks/useArtifacts";
import type { Appearance } from "../lib/artifacts";
import type { InteractionTab } from "./InteractionPanel";
import { useThreeScene } from "../hooks/useThreeScene";
import { useImport } from "../hooks/useImport";
import { useFileDrop } from "../hooks/useFileDrop";
import { useAppConfig } from "../state/appConfig";
import { formatDims } from "../lib/format";
import type { EngineFeature } from "../lib/ipc/engine";
import { engineFeatureAt, engineGetParams, engineSetFeature } from "../lib/ipc/engine";
import { ViewportContextMenu, type ParamRange } from "./ViewportContextMenu";

/** The four viewport tools. Orbit is the default active interaction mode. */
type Tool = "orbit" | "pan" | "measure";

/**
 * Resolved right-click menu state. `feature === null` is the empty-space variant
 * (view-level actions only); a feature with a `paramRange`/`paramName` renders
 * the parametric stepper, otherwise the inferred/non-parametric variant.
 */
type MenuState = {
  /** Anchor, viewport-relative px (right-click point minus the section's rect). */
  x: number;
  y: number;
  feature: EngineFeature | null;
  paramRange: ParamRange | null;
  paramName: string | null;
};

/** Trailing debounce window for committing stepper taps to the engine (ms). */
const STEP_COMMIT_MS = 150;
/** How long the transient "show dimensions" readout stays up (ms). */
const DIMS_LINGER_MS = 4000;

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

/**
 * Empty-state copy, keyed by the active left-pane tab. Kept out of JSX so guidance
 * is data-driven and the viewport copy stays in sync with the active tab.
 */
const EMPTY_STATE: Record<InteractionTab, { title: string; hint: string }> = {
  terminal: {
    title: "Open your favorite agentic CLI to begin",
    hint: "launch it in the terminal — your model renders here",
  },
  chat: {
    title: "Describe a part to begin",
    hint: "the engine renders your model here",
  },
};

function VTool({
  active = false,
  title,
  onClick,
  children,
}: {
  active?: boolean;
  title: string;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      aria-pressed={active}
      onClick={onClick}
      className={
        active
          ? "grid h-7.5 w-7.5 place-items-center rounded-lg bg-accent text-white shadow-[0_2px_8px_rgba(43,108,255,.5)]"
          : "grid h-7.5 w-7.5 place-items-center rounded-lg text-term-ink hover:bg-term-line"
      }
    >
      {children}
    </button>
  );
}

/** Props: the live artifacts (sans the inspector-only `refresh`) + active tab, owned by {@link AppShell}. */
type ViewportProps = Omit<ArtifactsState, "refresh"> & {
  activeTab: InteractionTab;
  selectedId?: string | null;
  hiddenIds?: ReadonlySet<string>;
  explode?: number;
  onExplodeChange?: (v: number) => void;
  partCount?: number;
  materialOverrides?: Record<string, Appearance>;
  building?: boolean;
  /** Quiet loading state: model.py exists but artifacts haven't loaded yet. Suppresses the empty prompt. */
  loading?: boolean;
};

/** Imperative handle exposed to the editor via `ref` for thumbnail capture. */
export interface ViewportHandle {
  /** Capture a normalized iso PNG of the current model, or null if none. */
  captureThumbnail: (w?: number, h?: number) => Promise<Blob | null>;
}

function Viewport(
  {
    model,
    glbBytes,
    buildId,
    activeTab,
    selectedId,
    hiddenIds,
    explode = 0,
    onExplodeChange,
    partCount = 0,
    materialOverrides = {},
    building = false,
    loading = false,
  }: ViewportProps,
  ref: React.ForwardedRef<ViewportHandle>,
) {
  const {
    containerRef,
    fit,
    hasModel,
    gpuLost,
    captureThumbnail,
    setMeasureEnabled,
    setOnPick,
    frameToFeature,
    setGridVisible,
    setGtaoEnabled,
    setAaEnabled,
    setSoftShadows,
  } = useThreeScene(
    glbBytes,
    buildId,
    model?.objects,
    { selectedId, hiddenIds },
    explode,
    materialOverrides,
  );

  // Expose the imperative capture to AppShell (leave-editor + post-build snapshots).
  useImperativeHandle(ref, () => ({ captureThumbnail }), [captureThumbnail]);

  // Keep the loading cover up until the scene has actually DRAWN the model:
  // useThreeScene.hasModel flips true only after the GLB is parsed + rendered,
  // not merely when the bytes land. Otherwise the grid + mesh pop in a beat
  // after the cover lifts. hasModel never resets, so rebuilds (which keep it
  // true and use the `building` overlay) never flash this cover.
  const showCover = loading || (model != null && !hasModel);

  const { config, setFlag } = useAppConfig();

  // The viewport <section> — both the menu's offset parent (it clamps against
  // this) and the frame we map client coords into for the menu anchor.
  const sectionRef = useRef<HTMLElement>(null);

  // Active interaction tool. Orbit is the live OrbitControls mode; pan is a
  // visual toggle; measure drives the click-to-measure overlay.
  const [tool, setTool] = useState<Tool>("orbit");

  // Right-click feature menu (null = closed). State lives here (not the scene
  // hook) because the menu is React UI; the hook just delivers the raw pick.
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [dimsReadout, setDimsReadout] = useState<string | null>(null);

  // Trailing-debounce timer for committing stepper taps; the dims auto-clear
  // timer. Both ref-held so a burst coalesces / re-arming is cheap, and both are
  // cleared on unmount so no stale callback fires after the viewport is gone.
  const stepTimer = useRef<number | null>(null);
  const dimsTimer = useRef<number | null>(null);

  // Click-to-measure follows the active tool: enable when "measure" is picked,
  // disable + clear when any other tool is selected. The cleanup also clears on
  // unmount so no stale markers/label survive a remount.
  useEffect(() => {
    if (tool === "measure") {
      setMeasureEnabled(true);
      return () => setMeasureEnabled(false);
    }
    setMeasureEnabled(false);
    return undefined;
  }, [tool, setMeasureEnabled]);

  // Register the right-click pick handler once. The scene hook raycasts and
  // hands us the hit point in engine (Z-up mm) space (or null on empty space),
  // plus client screen coords; we resolve the feature and open the menu. Every
  // engine call is failure-tolerant — a thrown/failed lookup falls back to the
  // empty/identify variant so the handler never rejects.
  useEffect(() => {
    setOnPick(async (p) => {
      const rect = sectionRef.current?.getBoundingClientRect();
      const x = p.screenX - (rect?.left ?? 0);
      const y = p.screenY - (rect?.top ?? 0);

      if (p.pointMm === null) {
        setMenu({ x, y, feature: null, paramRange: null, paramName: null });
        return;
      }

      let feature: EngineFeature | null = null;
      let paramName: string | null = null;
      let paramRange: ParamRange | null = null;
      try {
        feature = await engineFeatureAt(p.pointMm);
        // Parametric only when the feature is declared (not inferred) AND has a
        // driving param whose schema we can resolve to a range.
        if (feature && !feature.inferred && feature.driven_by.length > 0) {
          paramName = feature.driven_by[0];
          const raw = await engineGetParams();
          if (raw) {
            const schema = (JSON.parse(raw) as { schema?: Record<string, ParamRange> }).schema;
            paramRange = schema?.[paramName] ?? null;
          }
        }
      } catch {
        // Any failure → treat as a bare identify (or empty) menu; never throw.
        paramName = null;
        paramRange = null;
      }

      setMenu({ x, y, feature, paramRange, paramName });
    });
    return () => setOnPick(null);
  }, [setOnPick]);

  // A fresh build invalidates the menu's feature/value snapshot; close it.
  useEffect(() => setMenu(null), [buildId]);

  // Apply the persisted viewport feature flags to the live scene. Re-applied
  // whenever a flag flips AND after each build (`buildId` dep) — per-model setup
  // (frameToObject / setScale / setAoRadius) doesn't touch these toggles, so we
  // re-assert them so a disabled effect stays disabled across rebuilds. This is
  // the single appConfig→scene bridge (see appConfig.ts live-apply note).
  useEffect(() => {
    setGridVisible(config.grid);
    setGtaoEnabled(config.gtao);
    setAaEnabled(config.smaa);
    setSoftShadows(config.softShadows);
  }, [
    config.grid,
    config.gtao,
    config.smaa,
    config.softShadows,
    buildId,
    setGridVisible,
    setGtaoEnabled,
    setAaEnabled,
    setSoftShadows,
  ]);

  useEffect(
    () => () => {
      if (stepTimer.current != null) window.clearTimeout(stepTimer.current);
      if (dimsTimer.current != null) window.clearTimeout(dimsTimer.current);
    },
    [],
  );

  // ── menu action handlers ──

  // ± stepper: optimistically update the displayed value, then commit the new
  // value to the engine on a trailing debounce so a burst of taps coalesces into
  // one rebuild (the engine also coalesces commits within ~0.7s). The engine
  // fires `model-updated` → useArtifacts refreshes the GLB/manifest.
  const handleStep = (delta: number) => {
    setMenu((m) => {
      if (!m || !m.paramRange || !m.paramName || !m.feature) return m;
      const next = clamp(m.paramRange.value + delta, m.paramRange.min, m.paramRange.max);
      const name = m.feature.name;
      const key = m.paramName;
      if (stepTimer.current != null) window.clearTimeout(stepTimer.current);
      stepTimer.current = window.setTimeout(() => {
        void engineSetFeature(name, { [key]: next });
      }, STEP_COMMIT_MS);
      return { ...m, paramRange: { ...m.paramRange, value: next } };
    });
  };

  // Close the menu; the Inspector already surfaces this param's slider.
  const handleOpenInspector = () => setMenu(null);

  const handleFrame = () => {
    if (menu?.feature?.center) frameToFeature(menu.feature.center);
    setMenu(null);
  };

  // Show dimensions: compose a mono readout from the feature's bbox + center and
  // float it top-center for a few seconds (re-arming the auto-clear timer).
  const handleShowDimensions = () => {
    const f = menu?.feature;
    if (f) {
      const parts: string[] = [];
      if (f.bbox) parts.push(`${formatDims(f.bbox)} mm`);
      if (f.center) {
        const [cx, cy, cz] = f.center;
        parts.push(`@ ${cx.toFixed(1)}, ${cy.toFixed(1)}, ${cz.toFixed(1)}`);
      }
      setDimsReadout(`${f.name}  ·  ${parts.join("  ·  ") || "no extents"}`);
      if (dimsTimer.current != null) window.clearTimeout(dimsTimer.current);
      dimsTimer.current = window.setTimeout(() => setDimsReadout(null), DIMS_LINGER_MS);
    }
    setMenu(null);
  };

  const handleCopyReference = () => {
    if (menu?.feature) navigator.clipboard?.writeText(menu.feature.name);
    setMenu(null);
  };

  const handleFit = () => {
    fit();
    setMenu(null);
  };

  const handleToggleGrid = () => {
    setFlag("grid", !config.grid); // persisted; the appConfig effect re-applies to the scene
    setMenu(null);
  };

  const dims = model ? formatDims(model.bbox.size) : null;
  const mass = model ? `${model.mass.value.toFixed(1)} g` : null;

  const { note: importNote, importPath, pickAndImport } = useImport();
  const dragging = useFileDrop(importPath);

  return (
    <section
      ref={sectionRef}
      className="relative min-w-0 flex-1 overflow-hidden bg-[radial-gradient(120%_95%_at_50%_18%,#20242D_0%,#14171E_52%,#0D0F14_100%)]"
    >
      {/* film grain — kills gradient banding + adds tactility; sits behind the canvas */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='160'%20height='160'%3E%3Cfilter%20id='n'%3E%3CfeTurbulence%20type='fractalNoise'%20baseFrequency='0.85'%20numOctaves='2'%20stitchTiles='stitch'/%3E%3CfeColorMatrix%20type='saturate'%20values='0'/%3E%3C/filter%3E%3Crect%20width='100%25'%20height='100%25'%20filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />

      {/* three.js canvas mount — transparent so the graphite stage shows through */}
      <div ref={containerRef} className="absolute inset-0" />

      {dragging && (
        <div className="pointer-events-none absolute inset-0 z-20 grid place-items-center bg-[rgba(13,15,20,.55)] backdrop-blur-sm">
          <div className="flex flex-col items-center gap-2.5 rounded-2xl border-2 border-dashed border-[rgba(255,255,255,.28)] bg-[rgba(20,23,30,.6)] px-9 py-7 text-center">
            <Upload size={26} strokeWidth={1.6} className="text-term-ink" />
            <div className="text-body font-medium text-term-ink">Drop to import</div>
            <div className="font-mono text-caption text-[#6B7280]">
              STEP, BREP, or STL as a reference
            </div>
          </div>
        </div>
      )}

      {importNote && (
        <div
          className={`animate-rise absolute left-1/2 top-3.5 z-30 -translate-x-1/2 truncate rounded-lg border bg-scrim px-2.75 py-1.75 font-mono text-caption backdrop-blur-lg ${
            importNote.kind === "ok"
              ? "border-[rgba(25,169,87,.4)] text-engine"
              : "border-danger-line text-danger"
          }`}
        >
          {importNote.text}
        </div>
      )}

      {showCover && (
        <div className="pointer-events-none absolute inset-0 z-10 grid place-items-center bg-[radial-gradient(120%_95%_at_50%_18%,#20242D_0%,#14171E_52%,#0D0F14_100%)]">
          <Loader2
            size={26}
            strokeWidth={1.6}
            className="animate-spin text-term-ink-dim"
            aria-hidden
          />
        </div>
      )}
      {!showCover && !hasModel && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <div className="flex flex-col items-center gap-3 text-center">
            <span className="grid h-12 w-12 place-items-center rounded-xl border border-[rgba(255,255,255,.1)] bg-[rgba(20,23,30,.4)] text-term-ink-dim">
              <Box size={26} strokeWidth={1.5} />
            </span>
            <div className="text-body font-medium text-term-ink">
              {EMPTY_STATE[activeTab].title}
            </div>
            <div className="font-mono text-caption text-[#6B7280]">
              {EMPTY_STATE[activeTab].hint}
            </div>
            <button
              type="button"
              onClick={() => void pickAndImport()}
              className="pointer-events-auto mt-1 inline-flex h-8 items-center gap-1.75 rounded-lg border border-[rgba(255,255,255,.14)] bg-[rgba(20,23,30,.5)] px-3 text-body font-medium text-term-ink transition-colors duration-150 hover:border-[rgba(255,255,255,.28)]"
            >
              <Upload size={14} strokeWidth={1.8} />
              Import a model
            </button>
          </div>
        </div>
      )}

      <div className="absolute left-3.5 top-3.5 flex gap-1 rounded-xl border border-term-line bg-scrim p-1 backdrop-blur-lg">
        <VTool active={tool === "orbit"} title="Orbit" onClick={() => setTool("orbit")}>
          <Rotate3d size={16} strokeWidth={1.7} />
        </VTool>
        <VTool active={tool === "pan"} title="Pan" onClick={() => setTool("pan")}>
          <Move size={16} strokeWidth={1.7} />
        </VTool>
        <VTool
          active={tool === "measure"}
          title="Measure — click two points on the model"
          onClick={() => setTool("measure")}
        >
          <Ruler size={16} strokeWidth={1.7} />
        </VTool>
        <VTool title="Fit" onClick={fit}>
          <Maximize size={16} strokeWidth={1.7} />
        </VTool>
      </div>

      {/* explode control — viewport-only, shown for multi-part models. A pure
          viewport transform (0..100%); its value never reaches the engine. The
          track paints a live accent fill up to the current value (a dynamic CSS
          gradient — not expressible as a static class), and the thumb/hover/active
          treatment lives in the `.explode-range` component layer in index.css. */}
      {hasModel && partCount > 1 && (
        <div className="absolute right-3.5 top-3.5 flex items-center gap-2.5 rounded-xl border border-term-line bg-scrim px-3.25 py-2 backdrop-blur-lg">
          <span className="font-mono text-caption text-term-ink-dim">Explode</span>
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={explode}
            onChange={(e) => onExplodeChange?.(Number(e.target.value))}
            aria-label="Explode parts"
            className="explode-range w-28"
            style={{
              background: `linear-gradient(to right, rgba(43,108,255,0.7) 0%, rgba(43,108,255,0.7) ${explode}%, var(--color-term-line) ${explode}%, var(--color-term-line) 100%)`,
            }}
          />
          <span className="w-8 text-right font-mono text-caption text-term-ink">{explode}%</span>
        </div>
      )}

      {dimsReadout && (
        <div className="pointer-events-none absolute left-1/2 top-3.5 flex -translate-x-1/2 items-center gap-1.75 rounded-lg border border-[rgba(255,255,255,.12)] bg-scrim px-2.75 py-1.5 font-mono text-caption text-term-ink backdrop-blur-lg">
          <Ruler size={13} strokeWidth={1.7} className="text-term-ink-dim" />
          <span>{dimsReadout}</span>
        </div>
      )}

      {tool === "measure" && hasModel && (
        <div className="pointer-events-none absolute left-1/2 top-3.5 flex -translate-x-1/2 items-center gap-1.75 rounded-lg border border-accent-line bg-scrim px-2.75 py-1.5 text-caption text-term-ink backdrop-blur-lg">
          <span className="h-1.75 w-1.75 rounded-full bg-accent shadow-[0_0_8px_rgba(43,108,255,.7)]" />
          <span className="font-mono">click two points to measure</span>
          <span className="opacity-40">·</span>
          <span className="opacity-70">Esc to clear</span>
        </div>
      )}

      {building && (
        <div className="pointer-events-none absolute left-1/2 top-3.5 flex -translate-x-1/2 items-center gap-1.75 rounded-lg border border-accent-line bg-scrim px-2.75 py-1.5 text-caption text-term-ink backdrop-blur-lg">
          <span className="h-1.75 w-1.75 animate-pulse rounded-full bg-accent shadow-[0_0_8px_rgba(43,108,255,.7)]" />
          <span className="font-mono">Building model</span>
        </div>
      )}

      <div className="absolute bottom-3.5 left-3.5 flex items-center gap-2.75 rounded-xl border border-term-line bg-scrim px-3.25 py-2.25 font-mono text-xs text-term-ink backdrop-blur-lg">
        <span className="flex items-center gap-1.25 border-r border-[rgba(255,255,255,.14)] pr-2.75">
          <span className="h-2.25 w-2.25 rounded-xs bg-[#FF6B6B]" />
          <span className="h-2.25 w-2.25 rounded-xs bg-[#52DA8B]" />
          <span className="h-2.25 w-2.25 rounded-xs bg-[#74A6FF]" />
        </span>
        {dims ? (
          <>
            <span>
              <span className="font-semibold text-white">{dims}</span> mm
            </span>
            {mass && (
              <>
                <span className="opacity-50">·</span>
                <span>{mass}</span>
              </>
            )}
          </>
        ) : (
          <span className="opacity-60">no model</span>
        )}
      </div>

      {/* GPU device lost (sleep/wake, GPU reset): the scene can't recover in
          place, so cover the dead canvas and offer a full reload. Above every
          other overlay — nothing beneath is interactive anymore. */}
      {gpuLost && (
        <div className="absolute inset-0 z-40 grid place-items-center bg-[rgba(13,15,20,.72)] backdrop-blur-sm">
          <div className="flex flex-col items-center gap-3 rounded-2xl border border-term-line bg-[rgba(20,23,30,.6)] px-9 py-7 text-center">
            <span className="grid h-12 w-12 place-items-center rounded-xl border border-[rgba(255,255,255,.1)] bg-[rgba(20,23,30,.4)] text-term-ink-dim">
              <TriangleAlert size={24} strokeWidth={1.5} />
            </span>
            <div className="text-body font-medium text-term-ink">Viewport stopped rendering</div>
            <div className="font-mono text-caption text-[#6B7280]">
              the graphics device was lost, usually after sleep or a driver reset
            </div>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-1 inline-flex h-8 items-center gap-1.75 rounded-lg border border-[rgba(255,255,255,.14)] bg-[rgba(20,23,30,.5)] px-3 text-body font-medium text-term-ink transition-colors duration-150 hover:border-[rgba(255,255,255,.28)]"
            >
              <RotateCw size={14} strokeWidth={1.8} />
              Reload app
            </button>
          </div>
        </div>
      )}

      {/* right-click feature menu — anchored at the pick point, clamps itself
          against this <section> (its offset parent). Outside-click + Esc are
          handled inside the component. */}
      {menu && (
        <ViewportContextMenu
          x={menu.x}
          y={menu.y}
          feature={menu.feature}
          paramRange={menu.paramRange}
          paramName={menu.paramName}
          onStep={handleStep}
          onOpenInspector={handleOpenInspector}
          onFrame={handleFrame}
          onShowDimensions={handleShowDimensions}
          onCopyReference={handleCopyReference}
          onFit={handleFit}
          onResetView={handleFit}
          onToggleGrid={handleToggleGrid}
          onDismiss={() => setMenu(null)}
        />
      )}
    </section>
  );
}

// Memoized: re-renders only when its props (model/glbBytes/buildId/activeTab)
// actually change — not when the AppShell re-renders for unrelated reasons (e.g.
// inspector collapse). The three.js scene itself is driven imperatively by its
// hooks, independent of React's render cycle. forwardRef threads AppShell's ref
// down for thumbnail capture; memo wraps the forwarded component.
const ForwardedViewport = forwardRef<ViewportHandle, ViewportProps>(Viewport);
export default memo(ForwardedViewport);
