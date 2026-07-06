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
import { glbWorldToEngineMm, engineMmToGlbWorld } from "../lib/coords";
import { materialFromAppearance } from "./scene/materials";
import { setupEnvironment, type EnvHandle } from "./scene/environment";
import { buildLightRig, type LightRig } from "./scene/lighting";
import { buildComposer, type ComposerHandle } from "./scene/postprocessing";
import { buildGrid, type GridHandle } from "./scene/grid";
import { placeIsoCamera } from "./scene/isoFit";
import { refreshClipPlanes } from "./scene/camera";
import { createSelectionHighlight, type SelectionHighlight } from "./scene/highlight";
import { captureExplodeBasis, applyExplode, type ExplodeBasis } from "./scene/explode";
import {
  ACCENT,
  clearMeasurement,
  handleMeasureClick,
  markerRadius,
  updateMeasureLabel,
} from "./scene/measure";

/** Optional per-part selection/visibility inputs (default = none). */
export interface SceneSelection {
  selectedId?: string | null;
  hiddenIds?: ReadonlySet<string>;
}

const EMPTY_IDS: ReadonlySet<string> = new Set<string>();

/** Max pointer travel (px²) between down/up that still counts as a "click". */
const CLICK_SLOP_SQ = 5 * 5;

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

/** The contact-shadow ground lives here so the AO input pass, whose camera
 *  disables this layer, never samples it as an occluder. The main camera enables
 *  this layer so the ground still renders into the beauty pass. */
const FLOOR_LAYER = 1;
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
  env: EnvHandle;
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

    // IBL + light rig + post-processing pipeline (modular).
    const env = setupEnvironment(scene, renderer);
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
      env,
      lights,
      composer,
      grid,
      requestRender,
    };
    refs.current = handle;

    // ── measure pointer handlers (click = non-drag pointerdown→up) ──
    const onPointerDown = (e: PointerEvent) => {
      if (!measure.enabled || e.button !== 0) return;
      measure.downX = e.clientX;
      measure.downY = e.clientY;
    };
    const onPointerUp = (e: PointerEvent) => {
      if (!measure.enabled || e.button !== 0) return;
      const dx = e.clientX - measure.downX;
      const dy = e.clientY - measure.downY;
      // A drag (orbit) moves the pointer; only a near-stationary click picks.
      if (dx * dx + dy * dy > CLICK_SLOP_SQ) return;
      handleMeasureClick(handle, e);
      requestRender();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && measure.enabled) {
        clearMeasurement(measure);
        requestRender();
      }
    };
    // Right-click context menu: raycast and fire the pick callback if registered.
    const onContextMenu = (e: MouseEvent) => {
      e.preventDefault();
      if (!pick.onPick) return;
      const screenX = e.clientX;
      const screenY = e.clientY;
      if (modelGroup.children.length === 0) {
        pick.onPick({ pointMm: null, screenX, screenY });
        return;
      }
      const rect = renderer.domElement.getBoundingClientRect();
      measure.pointer.set(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1,
      );
      measure.raycaster.setFromCamera(measure.pointer, camera);
      const hits = measure.raycaster.intersectObject(modelGroup, true);
      pick.onPick({
        pointMm: hits.length ? glbWorldToEngineMm(hits[0].point, modelGroup) : null,
        screenX,
        screenY,
      });
    };
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointerup", onPointerUp);
    renderer.domElement.addEventListener("contextmenu", onContextMenu);
    window.addEventListener("keydown", onKeyDown);

    // Camera moved — user input or damping decay — so render.
    controls.addEventListener("change", requestRender);

    // Self-heal: any pointer over the viewport, or a window refocus / tab return,
    // repaints — so a missed trigger can't leave a stale frame on screen for long.
    // No periodic tick: cursor away + nothing changing ⇒ zero GPU frames.
    const onPointerMove = () => requestRender();
    const onFocus = () => requestRender();
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerenter", onPointerMove);
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);

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
    renderer.init().then(() => {
      if (disposed) return;
      renderer.setAnimationLoop(animate);
    });

    // ── container resize → renderer + camera aspect ──
    // Apply the live container size to the renderer + camera in one shot.
    // updateStyle=false: the canvas already fills via CSS (width/height:100%);
    // letting three.js rewrite the inline px size fights our layout.
    const applyResize = () => {
      const w = container.clientWidth || 1;
      const h = container.clientHeight || 1;
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

    return () => {
      observer.disconnect();
      if (resizeTimer) window.clearTimeout(resizeTimer);
      disposed = true;
      renderer.setAnimationLoop(null);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("contextmenu", onContextMenu);
      window.removeEventListener("keydown", onKeyDown);
      controls.removeEventListener("change", requestRender);
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerenter", onPointerMove);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
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
      env.dispose();
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
    if (!handle || handle.modelGroup.children.length === 0) return null;
    const box = new THREE.Box3().setFromObject(handle.modelGroup);
    if (box.isEmpty()) return null;

    // Throwaway camera: never touches handle.camera/controls. Enable FLOOR_LAYER
    // for the contact-shadow ground; GRID_LAYER stays off so no work-plane grid.
    const cam = new THREE.PerspectiveCamera(handle.camera.fov, w / h, 0.1, 100000);
    cam.layers.enable(FLOOR_LAYER);
    placeIsoCamera(cam, box);

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const pw = Math.round(w * dpr);
    const ph = Math.round(h * dpr);
    // Plain color+depth target (no MSAA): readback reads texture[0]; multisampled
    // attachments aren't readable, so we keep samples at the default 0.
    const rt = new THREE.RenderTarget(pw, ph, { depthBuffer: true });
    const prev = handle.renderer.getRenderTarget();
    try {
      handle.renderer.setRenderTarget(rt);
      // Plain render bypasses the node composer (TRAA/GTAO) — a single clean
      // beauty frame is plenty for a static iso card, and the composer's
      // temporal targets are sized to the live canvas, not this thumbnail.
      // Synchronous render() (not the r181-deprecated renderAsync): the renderer
      // is already init'd, and the readback's copyTextureToBuffer queues after
      // this render on the same GPU queue, so ordering is preserved.
      handle.renderer.render(handle.scene, cam);
      // three@0.184: readRenderTargetPixelsAsync RETURNS the pixel buffer (it
      // does not fill a passed-in array); for an RGBA8 target that's a Uint8Array.
      const buf = (await handle.renderer.readRenderTargetPixelsAsync(
        rt,
        0,
        0,
        pw,
        ph,
      )) as Uint8Array;
      return await pngFromPixels(buf, pw, ph);
    } catch (e) {
      console.warn("thumbnail capture failed", e);
      return null;
    } finally {
      handle.renderer.setRenderTarget(prev);
      rt.dispose();
      handle.requestRender(); // repaint the live view (which we never moved)
    }
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
 * The per-object subtrees of a loaded GLB, in show()/registry order. The
 * exporter nests all shown objects under one wrapper node whose children are the
 * per-object nodes; that wrapper is the shallowest node with exactly `n`
 * children (BFS). For n ≤ 1 the scene itself is returned as the single subtree.
 * Verified against build123d 0.10 export_gltf for n = 1, 2, 3.
 */
function objectSubtrees(scene: THREE.Object3D, n: number): THREE.Object3D[] {
  if (n <= 1) return [scene];
  const queue: THREE.Object3D[] = [scene];
  while (queue.length > 0) {
    const node = queue.shift() as THREE.Object3D;
    if (node.children.length === n) return node.children;
    queue.push(...node.children);
  }
  return scene.children; // fallback: never expected for a well-formed GLB
}

/** Index of the subtree whose object id matches `id` (−1 if none / no id). */
export function subtreeIndexForId(objects: ModelObject[] | undefined, id: string | null): number {
  if (!objects || id == null) return -1;
  return objects.findIndex((o) => o.id === id);
}

/**
 * Indices of every subtree the selection `id` resolves to: the exact leaf, or —
 * when `id` is an assembly-node prefix — all descendant leaves (path id starts
 * with `id + "/"`). The "/" guard stops "hinge" matching "hingeplate". Selecting
 * a group thus highlights every child mesh.
 */
export function subtreeIndicesForId(
  objects: ModelObject[] | undefined,
  id: string | null,
): number[] {
  if (!objects || id == null) return [];
  const prefix = id + "/";
  const out: number[] = [];
  objects.forEach((o, i) => {
    if (o.id === id || o.id.startsWith(prefix)) out.push(i);
  });
  return out;
}

/** Apply a hidden-id set to per-object subtrees (objects[i] ↔ subtrees[i]). */
export function applyVisibility(
  subtrees: THREE.Object3D[],
  objects: ModelObject[] | undefined,
  hiddenIds: ReadonlySet<string>,
): void {
  const objs = objects ?? [];
  subtrees.forEach((root, i) => {
    const id = objs[i]?.id;
    root.visible = id == null ? true : !hiddenIds.has(id);
  });
}

/** Dispose all geometries/materials/textures under `object`. */
function disposeObject(object: THREE.Object3D): void {
  object.traverse((node) => {
    const mesh = node as THREE.Mesh;
    if (mesh.isMesh) {
      mesh.geometry?.dispose();
      const mat = mesh.material;
      if (Array.isArray(mat)) mat.forEach((m) => disposeMaterial(m));
      else if (mat) disposeMaterial(mat);
    }
  });
}

function disposeMaterial(mat: THREE.Material): void {
  // Free any textures the material references before disposing it.
  for (const value of Object.values(mat as unknown as Record<string, unknown>)) {
    if (value && (value as THREE.Texture).isTexture) {
      (value as THREE.Texture).dispose();
    }
  }
  mat.dispose();
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

/**
 * Frame the camera so the model fills the view, then re-center the orbit target
 * + ground plane on it. Preserves the current viewing direction.
 *
 * Caches the model's largest dimension on `handle.frameMaxDim` so the render
 * loop can re-bracket near/far against the live zoom (see refreshClipPlanes) and
 * callers (GTAO / grid / ground sizing) can scale to the part without a second
 * `setFromObject` traversal. No-op when the model has no renderable geometry.
 */
function frameToObject(handle: SceneRefs): void {
  const { modelGroup: target, camera, controls } = handle;
  const box = new THREE.Box3().setFromObject(target);
  if (box.isEmpty()) return;

  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());

  // Seat the model in CAD fashion: tuck the part's corner right up against the
  // 0,0 origin cross so the whole body sits in ONE quadrant — the top-right of
  // the "+" — and never crosses the two major axis lines, rather than straddling
  // the origin. Each horizontal face is pushed flush to an axis:
  //   • X: min-X face → x=0, so the part lives in +X (screen right).
  //   • Z: max-Z face → z=0, so the part lives in −Z (screen "up"/away from the
  //     camera); together with +X that reads as the top-right quadrant.
  //   • Y (height): base → y=0 (the floor, where the contact shadow + grid live).
  // Then re-measure around the new bounds. modelGroup.position carries the full
  // offset, so the measure/pick coord transforms in coords.ts stay correct.
  target.position.x -= box.min.x;
  target.position.z -= box.max.z;
  target.position.y -= box.min.y;
  box.setFromObject(target);
  box.getSize(size);
  box.getCenter(center);

  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  handle.frameMaxDim = maxDim;
  const fov = (camera.fov * Math.PI) / 180;
  // Distance so the largest dimension fits, with comfortable padding.
  let dist = (maxDim / 2 / Math.tan(fov / 2)) * 1.7;
  dist = Math.max(dist, maxDim * 0.6);

  // Keep the existing view direction; just push the camera out along it.
  const dir = new THREE.Vector3().subVectors(camera.position, controls.target).normalize();
  if (dir.lengthSq() === 0) dir.set(1, 1, 1).normalize(); // iso fallback

  camera.position.copy(center).addScaledVector(dir, dist);
  controls.target.copy(center);
  // Bracket near/far around the framed scene. The render loop refreshes this
  // every frame from the live orbit distance, so this is just the initial slab.
  refreshClipPlanes(camera, controls.target, maxDim);
  controls.update();
}

/**
 * Encode a raw RGBA byte buffer (one `w`×`h` frame, 4 bytes/pixel) to a PNG blob.
 *
 * GPU pixel readback comes back bottom-up (origin at the lower-left), while a 2D
 * canvas' ImageData is top-down, so we copy source row `y` into destination row
 * `h-1-y` to flip vertically. Resolves `null` if a canvas isn't available or PNG
 * encoding fails, so the capture path always degrades to a placeholder.
 */
function pngFromPixels(buf: Uint8Array, w: number, h: number): Promise<Blob | null> {
  return new Promise((resolve) => {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) return resolve(null);

      // WebGPU readback rows are padded to a 256-byte stride; derive the real
      // stride from the buffer so non-64-aligned widths don't shear. (Packed
      // buffers reduce to w*4 naturally.) three's WebGPU copyTextureToBuffer
      // returns rows top-down (row 0 = top), matching the canvas, so copy each
      // row straight across with no vertical flip.
      const out = ctx.createImageData(w, h);
      const dstRowBytes = w * 4;
      const srcRowBytes = Math.floor(buf.length / h); // == aligned stride (or w*4 if packed)
      for (let y = 0; y < h; y++) {
        const srcStart = y * srcRowBytes;
        const dstStart = y * dstRowBytes;
        out.data.set(buf.subarray(srcStart, srcStart + dstRowBytes), dstStart);
      }
      ctx.putImageData(out, 0, 0);
      canvas.toBlob((blob) => resolve(blob), "image/png");
    } catch {
      resolve(null);
    }
  });
}
