/**
 * useThreeScene — owns the live three.js scene for the {@link Viewport}.
 *
 * Responsibilities:
 *   • Build renderer + scene + perspective camera + OrbitControls once per mount
 *     (StrictMode-double-init guarded via a ref) and tear it all down on unmount.
 *   • Track container size via a ResizeObserver → renderer.setSize + camera aspect.
 *   • Load a GLB from raw bytes with GLTFLoader.parse, swapping out the previous
 *     model group and applying a refined aluminum material to un-shaded meshes.
 *   • Frame the camera to the loaded model's bounding box (fit-to-object), and
 *     expose a `fit()` callback so the toolbar Fit button can re-frame on demand.
 *
 * The graphite radial background is rendered in CSS behind a transparent canvas
 * (see Viewport.tsx) so the WebGL clear stays transparent here.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { WebGPURenderer } from "three/webgpu";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { ModelObject } from "../lib/artifacts";
import { engineMmToGlbWorld } from "../lib/coords";
import { materialFromAppearance } from "./scene/materials";
import { setupEnvironment, type EnvHandle } from "./scene/environment";
import { buildLightRig, type LightRig } from "./scene/lighting";
import { buildComposer, type ComposerHandle } from "./scene/postprocessing";
import { buildGrid, type GridHandle } from "./scene/grid";
import { refreshClipPlanes } from "./scene/camera";
import { createSelectionHighlight, type SelectionHighlight } from "./scene/highlight";
import { captureExplodeBasis, applyExplode, type ExplodeBasis } from "./scene/explode";
import { FLOOR_LAYER, captureThumbnail as captureThumbnailImpl } from "./scene/thumbnail";
import { ACCENT, clearMeasurement, markerRadius, updateMeasureLabel } from "./scene/measure";
import {
  objectSubtrees,
  subtreeIndexForId,
  subtreeIndicesForId,
  applyVisibility,
  frameToObject,
} from "./scene/sceneGraph";
import { disposeObject, disposeMaterial } from "./scene/dispose";
import { attachInteraction } from "./scene/interaction";

export { subtreeIndexForId, subtreeIndicesForId, applyVisibility };

/** Optional per-part selection/visibility inputs (default = none). */
export interface SceneSelection {
  selectedId?: string | null;
  hiddenIds?: ReadonlySet<string>;
}

const EMPTY_IDS: ReadonlySet<string> = new Set<string>();

/**
 * Quiet window (ms) a resize must hold before we re-`setSize` the renderer. On
 * WebGPURenderer, setSize reallocates the node-pipeline render targets (scene
 * MRT + temporal GTAO + TRAA history); doing that every frame of a continuous
 * resize (window drag, or the inspector's 340ms width slide) leaves the
 * composited output blank for the whole gesture. We coalesce the burst into one
 * setSize once the size settles instead. The canvas fills via CSS, so it
 * stretches to the live box meanwhile (scene stays visible), then snaps crisp.
 */
const RESIZE_SETTLE_MS = 100;

/**
 * Frames to keep rendering after the last change before the loop sleeps. The
 * pipeline's temporal passes (32-sample GTAO + TRAA) denoise/anti-alias by
 * accumulating across consecutive frames, so a single post-change frame would
 * rest noisier and more aliased than the always-on loop. ~60 frames (≈1s at
 * 60fps) lets them converge to the same clean image, then it sleeps. Tunable:
 * lower for more savings if convergence proves faster.
 */
const CONVERGENCE_FRAMES = 60;

/** The work-plane grid lives here, alone, so it renders in its own pass (the
 *  grid camera sees ONLY this layer) and never enters the TRAA-jittered scene
 *  pass — temporal AA dissolves its fine minor lines. Composited back over the
 *  beauty with a model-depth occlusion test (see buildComposer). */
const GRID_LAYER = 2;

/**
 * A right-click pick event: the hit point in engine (build123d Z-up mm) space,
 * or null if the ray missed the model (or no model is loaded). Screen coords are
 * always present so callers can anchor a context menu to the cursor.
 */
export interface PickEvent {
  pointMm: [number, number, number] | null;
  screenX: number;
  screenY: number;
}

/**
 * Imperatively-driven measure state, kept entirely off React. The label is a
 * single absolutely-positioned <div> the hook owns: its world-space anchor is
 * the A–B midpoint, re-projected to screen every RAF frame (no per-frame React
 * state). Markers + line are three.js objects parented to a dedicated group so
 * they orbit with the model and dispose cleanly.
 */
export interface MeasureState {
  /** Container for marker spheres + the A–B line; child of the scene. */
  group: THREE.Group;
  /** Frosted distance pill, appended to the canvas container. */
  label: HTMLDivElement;
  /** Placed world-space hit points (0, 1, or 2). */
  points: THREE.Vector3[];
  /** Marker spheres, parallel to `points`. */
  markers: THREE.Mesh[];
  /** The A–B line, present only once two points exist. */
  line: THREE.Line | null;
  /** Whether measure mode is active (pointer handlers raycast when true). */
  enabled: boolean;
  /** Reusable raycaster + pointer NDC, allocated once. */
  raycaster: THREE.Raycaster;
  pointer: THREE.Vector2;
  /** Pointerdown bookkeeping for click-vs-drag discrimination. */
  downX: number;
  downY: number;
  /** Shared sphere geometry for markers (disposed on teardown). */
  markerGeo: THREE.SphereGeometry;
}

/** Right-click pick callback registry, kept off React state. */
interface PickState {
  onPick: ((p: PickEvent) => void) | null;
}

/** Internal mutable scene handle kept off React state (refs only). */
export interface SceneRefs {
  renderer: WebGPURenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  /** Model-only camera (FLOOR_LAYER disabled) feeding the GTAO input pass. */
  aoCamera: THREE.PerspectiveCamera;
  /** Grid-only camera (GRID_LAYER) feeding the separate, un-jittered grid pass. */
  gridCamera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  /** Group holding the current model; cleared + repopulated on each GLB load. */
  modelGroup: THREE.Group;
  /** Largest dimension of the framed model. Set by frameToObject; lets the
   *  render loop re-bracket near/far against the live zoom without a per-frame
   *  bounding-box traversal. */
  frameMaxDim: number;
  /** Contact-shadow ground disc, repositioned under each loaded model. */
  ground: THREE.Mesh;
  /** Click-to-measure overlay state (markers, line, label). */
  measure: MeasureState;
  /** Right-click pick callback registry. */
  pick: PickState;
  lights: LightRig;
  composer: ComposerHandle;
  grid: GridHandle;
  /** Refill the on-demand render budget. Called by every scene mutation so the
   *  gated loop wakes and renders a convergence burst, then sleeps. */
  requestRender: () => void;
}

export interface UseThreeScene {
  /** Attach to the element that should host the <canvas>. */
  containerRef: React.RefObject<HTMLDivElement | null>;
  /** Re-frame the camera to the current model's bounding box. */
  fit: () => void;
  /** True once a model has been loaded into the scene. */
  hasModel: boolean;
  /**
   * True after the GPU device/context is lost (sleep/wake, GPU reset). The
   * pipeline can't recover in place; the loop is stopped and the caller should
   * surface a reload affordance.
   */
  gpuLost: boolean;
  /**
   * Enable/disable click-to-measure. Disabling also clears any in-progress
   * measurement. Safe to call before the scene mounts (idempotent).
   */
  setMeasureEnabled: (enabled: boolean) => void;
  /** Clear the current measurement (markers, line, label) without disabling. */
  clearMeasure: () => void;
  /**
   * Register a callback that fires on every right-click on the viewport canvas.
   * The callback receives a {@link PickEvent} with the hit point in engine
   * (build123d Z-up mm) coordinates, or `null` if the ray missed.
   * Pass `null` to unregister.
   */
  setOnPick: (cb: ((p: PickEvent) => void) | null) => void;
  /**
   * Re-center the orbit target on a build123d Z-up mm point and pulse a cobalt
   * marker there (auto-removed after ~1200 ms). No-op if the scene is not yet
   * mounted.
   */
  frameToFeature: (centerMm: [number, number, number]) => void;
  /** Show/hide the work-plane grid. No-op if the scene is not yet mounted. */
  setGridVisible: (v: boolean) => void;
  /** Enable/disable the GTAO ambient-occlusion pass live (settings feature toggle). */
  setGtaoEnabled: (v: boolean) => void;
  /** Enable/disable the TRAA anti-aliasing pass live (settings feature toggle). */
  setAaEnabled: (v: boolean) => void;
  /** Toggle soft (PCF) vs hard contact shadows live (settings feature toggle). */
  setSoftShadows: (v: boolean) => void;
  /**
   * Render a normalized iso snapshot of the current model to a PNG blob, framed
   * fresh on a throwaway camera + render target so the user's live view (camera,
   * controls, post-processing) is never disturbed. Includes the contact-shadow
   * ground but not the work-plane grid; the transparent clear yields a PNG with
   * alpha around the part. Resolves `null` when there's no model, or on any GPU
   * failure (the caller falls back to a placeholder).
   */
  captureThumbnail: (w?: number, h?: number) => Promise<Blob | null>;
}

/**
 * @param glbBytes Raw GLB bytes for the current build, or null for empty state.
 * @param buildId  Changes whenever a *new* GLB should be loaded (load trigger).
 * @param objects  Per-object metadata (including appearance) from the model manifest.
 */
export function useThreeScene(
  glbBytes: Uint8Array | null,
  buildId: number,
  objects: ModelObject[] | undefined,
  selection: SceneSelection = {},
  explode = 0,
  materialOverrides: Record<string, import("../lib/artifacts").Appearance> = {},
): UseThreeScene {
  const { selectedId = null, hiddenIds = EMPTY_IDS } = selection;
  const containerRef = useRef<HTMLDivElement>(null);
  const refs = useRef<SceneRefs | null>(null);
  // StrictMode runs effects twice in dev; we only ever build one renderer.
  const initedRef = useRef(false);
  const [hasModel, setHasModel] = useState(false);
  const [gpuLost, setGpuLost] = useState(false);

  // Latest per-object appearance, read inside the GLB onLoad callback. Kept in a
  // ref so appearance updates don't retrigger the load effect (which keys on
  // buildId); model.json and the GLB always arrive together for a given build.
  const objectsRef = useRef<ModelObject[] | undefined>(objects);
  objectsRef.current = objects;

  const overridesRef = useRef(materialOverrides);
  overridesRef.current = materialOverrides;

  // The per-object subtrees of the *current* loaded GLB, in objects[] order.
  // Captured at load time so visibility/selection effects can mutate them
  // without re-running the load effect.
  const subtreesRef = useRef<THREE.Object3D[]>([]);
  const highlightRef = useRef<SelectionHighlight | null>(null);

  // Assembled-state explode basis, recaptured each time a new GLB is framed.
  const explodeBasisRef = useRef<ExplodeBasis | null>(null);
  const explodeRef = useRef<number>(explode);
  explodeRef.current = explode;

  // Current selection/visibility, read inside the async GLB onLoad (which fires
  // after React has already flushed effects, so it can't rely on effect deps).
  const hiddenIdsRef = useRef<ReadonlySet<string>>(hiddenIds);
  hiddenIdsRef.current = hiddenIds;
  const selectedIdRef = useRef<string | null>(selectedId);
  selectedIdRef.current = selectedId;

  /* ── scene init / teardown ──────────────────────────────────────────── */
  useEffect(() => {
    const container = containerRef.current;
    if (!container || initedRef.current) return;
    initedRef.current = true;

    const width = container.clientWidth || 1;
    const height = container.clientHeight || 1;

    const renderer = new WebGPURenderer({
      antialias: false, // TRAA handles anti-aliasing
      alpha: true, // transparent clear so the CSS graphite gradient shows through
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.setClearColor(0x000000, 0);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);
    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";

    const scene = new THREE.Scene();

    const camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 5000);
    // Seed a true isometric view: equal offsets on all three axes seat the
    // camera on the model's front-top-right corner — ~35.26° above the ground
    // plane, 45° around — so the first framed model reads as a clean CAD iso.
    // frameToObject keeps this direction and only dollies along it to fit, so
    // the load orientation is set entirely here.
    camera.position.set(140, 140, 140);
    // The main camera renders the model (layer 0) + the contact-shadow ground
    // (FLOOR_LAYER), but NOT the grid (GRID_LAYER) — the grid draws in its own
    // pass. Clones below inherit this mask, then narrow it.
    camera.layers.enable(FLOOR_LAYER);

    // AO input camera: tracks the main camera but does NOT render FLOOR_LAYER,
    // so GTAO's depth/normal contain only the model (floor can't occlude walls).
    const aoCamera = camera.clone() as THREE.PerspectiveCamera;
    aoCamera.layers.disable(FLOOR_LAYER);

    // Grid camera: tracks the main camera but renders ONLY GRID_LAYER, so the
    // work-plane grid draws in a separate, un-jittered pass kept out of TRAA
    // (temporal AA was averaging its fine minor lines into the background).
    const gridCamera = camera.clone() as THREE.PerspectiveCamera;
    gridCamera.layers.set(GRID_LAYER);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.rotateSpeed = 0.85;
    controls.target.set(0, 0, 0);

    // Light rig + post-processing pipeline (modular). The IBL environment is
    // attached in the renderer.init() handler below: PMREMGenerator.fromScene
    // throws on an uninitialized backend, and on the WebGL fallback path (no
    // WebGPU, e.g. Intel builds under Rosetta) init never wins that race.
    let env: EnvHandle | null = null;
    const lights = buildLightRig(scene);
    renderer.toneMapping = THREE.NeutralToneMapping; // neutral product-viz tone map
    const composer = buildComposer(renderer, scene, camera, aoCamera, gridCamera);
    const grid = buildGrid(scene);
    grid.setLayer(GRID_LAYER);

    // ── subtle ground contact shadow ──
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(4000, 4000),
      new THREE.ShadowMaterial({ opacity: 0.22 }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    ground.layers.set(FLOOR_LAYER); // floor only — excluded from the AO + grid passes
    scene.add(ground);

    const modelGroup = new THREE.Group();
    scene.add(modelGroup);

    // ── click-to-measure overlay (markers + line live in-scene; label in DOM) ──
    const measureGroup = new THREE.Group();
    scene.add(measureGroup);

    const label = document.createElement("div");
    label.className = MEASURE_LABEL_CLASS;
    // Positioned imperatively each frame via transform; hidden until 2 points.
    label.style.cssText =
      "position:absolute;left:0;top:0;display:none;pointer-events:none;" +
      "will-change:transform;z-index:5;";
    container.appendChild(label);

    const measure: MeasureState = {
      group: measureGroup,
      label,
      points: [],
      markers: [],
      line: null,
      enabled: false,
      raycaster: new THREE.Raycaster(),
      pointer: new THREE.Vector2(),
      downX: 0,
      downY: 0,
      markerGeo: new THREE.SphereGeometry(1, 20, 20),
    };

    const pick: PickState = { onPick: null };

    // On-demand render budget: frames still owed before the loop may sleep. Kept
    // as a closure var (single source of truth); requestRender on the handle lets
    // the hook's callbacks/effects refill it via refs.current.
    let framesRemaining = CONVERGENCE_FRAMES; // initial paint
    const requestRender = () => {
      framesRemaining = CONVERGENCE_FRAMES;
    };

    const handle: SceneRefs = {
      renderer,
      scene,
      camera,
      aoCamera,
      gridCamera,
      controls,
      modelGroup,
      frameMaxDim: 1,
      ground,
      measure,
      pick,
      lights,
      composer,
      grid,
      requestRender,
    };
    refs.current = handle;

    // Camera moved — user input or damping decay — so render.
    controls.addEventListener("change", requestRender);

    // Pointer/keyboard/context-menu/pick/focus wiring lives in its own module
    // (see scene/interaction.ts) so this effect stays about scene construction.
    const detachInteraction = attachInteraction(handle);

    const animate = () => {
      // Always apply damping (cheap). This also fires controls' 'change' event
      // while the camera is still moving, refilling the budget via the listener
      // above — so a settling orbit keeps rendering until it stops.
      controls.update();
      if (framesRemaining <= 0) return; // idle — skip the whole GPU pipeline
      framesRemaining--;
      // Re-project the A–B midpoint to screen and move the label imperatively
      // (no React state per frame) so it tracks the model as the camera orbits.
      updateMeasureLabel(handle);
      // Re-bracket the depth slab around the part at the CURRENT orbit distance.
      // Frozen near/far (set once at frame time) let a zoom-out dolly push the
      // model past the far plane, clipping it and revealing the black background
      // as a "wall" creeping over the part. Recompute before the cameras mirror.
      if (handle.modelGroup.children.length > 0) {
        refreshClipPlanes(camera, controls.target, handle.frameMaxDim);
      }
      // Mirror the main camera onto the AO + grid cameras each frame, then
      // re-mask: copy() carries the full layer mask back, so each must re-narrow.
      handle.aoCamera.copy(camera); // position/rotation/projection mirror
      handle.aoCamera.layers.disable(FLOOR_LAYER); // model-only
      handle.gridCamera.copy(camera);
      handle.gridCamera.layers.set(GRID_LAYER); // grid-only
      handle.composer.render(); // RenderPipeline.render() — synchronous; renderer is init'd
    };

    // WebGPURenderer needs async init before the first render.
    let disposed = false;

    // GPU loss (webglcontextlost on the WebGL fallback, device.lost on WebGPU —
    // three routes both here after preventDefault-ing the WebGL event) is not
    // recoverable in place: stop the loop instead of pushing frames into a dead
    // context, and surface the reload overlay via gpuLost.
    const defaultOnDeviceLost = renderer.onDeviceLost.bind(renderer);
    renderer.onDeviceLost = (info) => {
      defaultOnDeviceLost(info); // logs + marks the renderer dead
      if (disposed) return;
      renderer.setAnimationLoop(null);
      setGpuLost(true);
    };

    renderer.init().then(() => {
      if (disposed) return;
      env = setupEnvironment(scene, renderer);
      requestRender(); // repaint now that the IBL contributes
      renderer.setAnimationLoop(animate);
    });

    // ── container resize → renderer + camera aspect ──
    // Apply the live container size to the renderer + camera in one shot.
    // updateStyle=false: the canvas already fills via CSS (width/height:100%);
    // letting three.js rewrite the inline px size fights our layout.
    const applyResize = () => {
      const w = container.clientWidth || 1;
      const h = container.clientHeight || 1;
      // Re-read DPR: dragging the window to a display with a different scale
      // factor changes devicePixelRatio without touching the container's CSS
      // size (the matchMedia watcher below funnels through this same path).
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      handle.composer.setSize(w, h);
      requestRender();
    };
    // Coalesce a resize burst into a single setSize once it settles (see
    // RESIZE_SETTLE_MS): reallocating the WebGPU post-processing targets every
    // frame of a continuous resize blanks the composited output for the whole
    // gesture. The animation loop keeps painting; the canvas (CSS 100%) stretches
    // to the live box until applyResize snaps it crisp here.
    let resizeTimer = 0;
    const onResize = () => {
      if (resizeTimer) window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(applyResize, RESIZE_SETTLE_MS);
    };
    const observer = new ResizeObserver(onResize);
    observer.observe(container);

    // DPR changes never fire the ResizeObserver (the container's CSS size is
    // unchanged), so watch them with the standard one-shot matchMedia loop:
    // each query matches only the current DPR, so its 'change' fires once on a
    // display switch and must be re-armed against the new value.
    let dprQuery: MediaQueryList | null = null;
    function onDprChange() {
      armDprQuery();
      onResize(); // settle-debounced; applyResize re-reads the live DPR
    }
    function armDprQuery() {
      dprQuery?.removeEventListener("change", onDprChange);
      dprQuery = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
      dprQuery.addEventListener("change", onDprChange);
    }
    armDprQuery();

    return () => {
      observer.disconnect();
      dprQuery?.removeEventListener("change", onDprChange);
      if (resizeTimer) window.clearTimeout(resizeTimer);
      disposed = true;
      renderer.setAnimationLoop(null);
      detachInteraction();
      controls.removeEventListener("change", requestRender);
      controls.dispose();
      disposeObject(modelGroup);
      ground.geometry.dispose();
      (ground.material as THREE.Material).dispose();
      // Measure overlay: clear in-progress geometry, then free shared resources.
      clearMeasurement(measure);
      measure.markerGeo.dispose();
      if (label.parentNode === container) container.removeChild(label);
      highlightRef.current?.clear();
      highlightRef.current = null;
      handle.composer.dispose();
      grid.dispose();
      lights.dispose();
      env?.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
      refs.current = null;
      initedRef.current = false;
    };
    // One-time setup; containerRef is stable for the component's lifetime.
  }, []);

  /* ── fit-to-object ──────────────────────────────────────────────────── */
  const fit = useCallback(() => {
    const handle = refs.current;
    if (!handle) return;
    if (handle.modelGroup.children.length === 0) return;
    frameToObject(handle);
    handle.requestRender();
  }, []);

  /* ── measure mode toggle / clear ────────────────────────────────────── */
  const setMeasureEnabled = useCallback((enabled: boolean) => {
    const handle = refs.current;
    if (!handle) return;
    handle.measure.enabled = enabled;
    // Disabling always clears any half-finished or completed measurement.
    if (!enabled) clearMeasurement(handle.measure);
    handle.requestRender();
  }, []);

  const clearMeasure = useCallback(() => {
    const handle = refs.current;
    if (!handle) return;
    clearMeasurement(handle.measure);
    handle.requestRender();
  }, []);

  /* ── right-click pick callback ──────────────────────────────────────── */
  const setOnPick = useCallback((cb: ((p: PickEvent) => void) | null) => {
    const handle = refs.current;
    if (!handle) return;
    handle.pick.onPick = cb;
  }, []);

  /* ── frameToFeature ─────────────────────────────────────────────────── */
  const frameToFeature = useCallback((centerMm: [number, number, number]) => {
    const handle = refs.current;
    if (!handle) return;

    const world = engineMmToGlbWorld(centerMm, handle.modelGroup);

    // Cobalt pulse marker — reusing the measure-marker idiom exactly.
    const marker = new THREE.Mesh(
      handle.measure.markerGeo,
      new THREE.MeshBasicMaterial({ color: ACCENT, depthTest: false, transparent: true }),
    );
    marker.renderOrder = 999;
    marker.position.copy(world);
    marker.scale.setScalar(markerRadius(handle.modelGroup) * 1.6);
    handle.scene.add(marker);

    window.setTimeout(() => {
      // Stale handle (unmounted or re-inited mid-pulse): nothing live to clean up.
      if (refs.current !== handle) return;
      handle.scene.remove(marker);
      (marker.material as THREE.Material).dispose();
      // Geometry is the shared markerGeo; NOT disposed here.
      handle.requestRender();
    }, 1200);

    // Re-center the orbit target on the feature.
    handle.controls.target.copy(world);
    handle.controls.update();
    handle.requestRender();
  }, []);

  /* ── grid visibility ────────────────────────────────────────────────── */
  const setGridVisible = useCallback((v: boolean) => {
    refs.current?.grid.setVisible(v);
    refs.current?.requestRender();
  }, []);

  /* ── viewport feature toggles (settings flags) ──────────────────────── */
  const setGtaoEnabled = useCallback((v: boolean) => {
    refs.current?.composer.setGtaoEnabled(v);
    refs.current?.requestRender();
  }, []);
  const setAaEnabled = useCallback((v: boolean) => {
    refs.current?.composer.setAaEnabled(v);
    refs.current?.requestRender();
  }, []);
  const setSoftShadows = useCallback((v: boolean) => {
    refs.current?.lights.setSoftShadows(v);
    refs.current?.requestRender();
  }, []);

  /* ── thumbnail capture (off-screen, leaves the live view untouched) ──── */
  const captureThumbnail = useCallback(async (w = 768, h = 576): Promise<Blob | null> => {
    const handle = refs.current;
    if (!handle) return null;
    return await captureThumbnailImpl(handle, w, h);
  }, []);

  /* ── GLB load on new buildId ────────────────────────────────────────── */
  useEffect(() => {
    const handle = refs.current;
    if (!handle || !glbBytes || buildId < 0) return;

    let cancelled = false;
    const loader = new GLTFLoader();

    // GLTFLoader.parse wants an ArrayBuffer; slice to the exact byte range so a
    // shared/oversized backing buffer doesn't corrupt the parse.
    const arrayBuffer = glbBytes.buffer.slice(
      glbBytes.byteOffset,
      glbBytes.byteOffset + glbBytes.byteLength,
    ) as ArrayBuffer;

    loader.parse(
      arrayBuffer,
      "",
      (gltf) => {
        if (cancelled || !refs.current) return;
        const h = refs.current;

        // Old meshes are about to be disposed — drop their highlight bookkeeping
        // so clear() never touches disposed materials.
        highlightRef.current?.clear();

        // Clear the previous model group.
        for (let i = h.modelGroup.children.length - 1; i >= 0; i--) {
          const child = h.modelGroup.children[i];
          h.modelGroup.remove(child);
          disposeObject(child);
        }

        // Per-object materials by ORDER join. export_gltf emits one mesh per
        // shown child, in order; the shown objects are the children of the
        // shallowest node with exactly objects.length children (verified for
        // N=1,2,3). Apply objects[i].appearance to every mesh under subtree i.
        const objs = objectsRef.current ?? [];
        const subtrees = objectSubtrees(gltf.scene, objs.length);
        subtreesRef.current = subtrees;
        gltf.scene.traverse((node) => {
          const mesh = node as THREE.Mesh;
          if (mesh.isMesh) {
            mesh.castShadow = true;
            mesh.receiveShadow = true;
          }
        });
        subtrees.forEach((root, i) => {
          const ov = objs[i] ? overridesRef.current[objs[i].id] : undefined;
          const material = materialFromAppearance(ov ?? objs[i]?.appearance);
          root.traverse((node) => {
            const mesh = node as THREE.Mesh;
            if (mesh.isMesh) {
              const prev = mesh.material;
              mesh.material = material;
              if (prev && !Array.isArray(prev)) disposeMaterial(prev);
            }
          });
        });

        // Re-apply current visibility + selection to the freshly built subtrees.
        // GLTFLoader.parse's onLoad runs after React has flushed the effects
        // below (which fire at commit time), so on a rebuild they can't see
        // these new subtrees — apply here, where they exist, like the materials.
        applyVisibility(subtrees, objs, hiddenIdsRef.current);
        if (!highlightRef.current) highlightRef.current = createSelectionHighlight();
        // A selected assembly node lights up every descendant subtree.
        const selIdxs = subtreeIndicesForId(objs, selectedIdRef.current);
        highlightRef.current.applyMany(selIdxs.map((i) => subtrees[i]));

        // A fresh model invalidates any markers placed on the old geometry.
        clearMeasurement(h.measure);

        h.modelGroup.add(gltf.scene);
        // Seats the model (corner at the 0,0 origin, base on y=0) and caches the
        // framed size on h.frameMaxDim; reuse that below instead of recomputing
        // setFromObject (one fewer O(vertices) traversal per build).
        frameToObject(h);

        // Capture the assembled basis (factor 0) AFTER framing, then apply the
        // current explode factor so a reload keeps the user's spread.
        h.modelGroup.updateMatrixWorld(true);
        explodeBasisRef.current = captureExplodeBasis(subtrees);
        applyExplode(subtrees, explodeBasisRef.current, explodeRef.current);

        // Per-model GTAO setup + break the y=0 coplanarity that GTAO amplifies.
        // GTAO re-renders the scene (incl. the contact-shadow ground) into its own
        // OPAQUE depth/normal G-buffer; with the model base dropped to y=0 and the
        // ground at y=0, the ground won the coplanar depth tie at the bore-bottom
        // rim and its flat up-normal crawled into the bore-wall AO under motion.
        const maxDim = h.frameMaxDim; // set by frameToObject above
        // 1. AO radius + a matching view-space thickness gate, scaled to the part
        //    (the gate was dead at the hardcoded 1.0 on this ~0.09-unit model).
        h.composer.setAoRadius(maxDim * 0.05);
        // 2. Sink the ground a hair below the base so it is no longer coplanar
        //    (~0.1% of model size: invisible in the blurred contact shadow, but
        //    far beyond depth-buffer resolution, so the depth tie can't form).
        h.ground.position.y = -maxDim * 1e-3;

        // Scale the work-plane grid (cell/section/extent) to the part size.
        h.grid.setScale(maxDim);

        // Scale the contact-shadow rig to the part so the shadow camera frames it
        // (the hardcoded ±200/far-800 default only suited ~100-unit models).
        h.lights.setShadowExtent(maxDim);

        setHasModel(true);
        h.requestRender();
      },
      (err) => {
        // Bad/partial GLB — leave the previous model (or empty state) in place.
        console.error("GLB parse failed", err);
      },
    );

    return () => {
      cancelled = true;
    };
  }, [glbBytes, buildId]);

  // Live-toggle: re-apply visibility when the hidden set changes while a model
  // is loaded. Load-time application happens in the GLB onLoad above.
  useEffect(() => {
    applyVisibility(subtreesRef.current, objectsRef.current, hiddenIds);
    refs.current?.requestRender();
  }, [hiddenIds]);

  // Live-select: re-highlight when the selection changes while a model is
  // loaded. Load-time application happens in the GLB onLoad above.
  useEffect(() => {
    if (!highlightRef.current) highlightRef.current = createSelectionHighlight();
    const hl = highlightRef.current;
    const idxs = subtreeIndicesForId(objectsRef.current, selectedId);
    hl.applyMany(idxs.map((i) => subtreesRef.current[i]));
    refs.current?.requestRender();
  }, [selectedId]);

  // Live-explode: re-apply the radial offset when the factor changes while a
  // model is loaded. Load-time application happens in the GLB onLoad above.
  useEffect(() => {
    const basis = explodeBasisRef.current;
    if (basis) applyExplode(subtreesRef.current, basis, explode);
    refs.current?.requestRender();
  }, [explode]);

  // Live-material: recolor part subtrees when the override map changes while a
  // model is loaded. Re-asserts selection highlight afterward so a recolor under
  // the current selection keeps its tint.
  useEffect(() => {
    const objs = objectsRef.current ?? [];
    const subtrees = subtreesRef.current;
    subtrees.forEach((root, i) => {
      const id = objs[i]?.id;
      const ov = id ? materialOverrides[id] : undefined;
      const material = materialFromAppearance(ov ?? objs[i]?.appearance);
      root.traverse((node) => {
        const mesh = node as THREE.Mesh;
        if (mesh.isMesh) {
          const prev = mesh.material;
          mesh.material = material;
          if (prev && !Array.isArray(prev)) disposeMaterial(prev);
        }
      });
    });
    if (highlightRef.current) {
      const selIdxs = subtreeIndicesForId(objs, selectedIdRef.current);
      if (selIdxs.length > 0) highlightRef.current.applyMany(selIdxs.map((i) => subtrees[i]));
    }
    refs.current?.requestRender();
  }, [materialOverrides]);

  return {
    containerRef,
    fit,
    hasModel,
    gpuLost,
    setMeasureEnabled,
    clearMeasure,
    setOnPick,
    frameToFeature,
    setGridVisible,
    setGtaoEnabled,
    setAaEnabled,
    setSoftShadows,
    captureThumbnail,
  };
}

/**
 * Tailwind classes for the frosted distance pill — matches the viewport's other
 * floating overlays (dock / HUD): dark glassy panel, hairline border, IBM Plex
 * Mono numerics. Centered on its anchor via the -50% transform set per frame.
 */
const MEASURE_LABEL_CLASS =
  "rounded-lg border border-accent-line " +
  "bg-[rgba(20,23,30,.72)] px-2 py-0.75 font-mono text-caption " +
  "font-medium leading-none text-white shadow-[0_2px_10px_rgba(0,0,0,.35)] " +
  "backdrop-blur-md";
