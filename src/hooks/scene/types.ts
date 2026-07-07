/**
 * Shared scene types + render-layer constants for {@link useThreeScene} and its
 * `scene/*` leaf modules. Lives here (not in the hook) so the leaf modules never
 * import back from the hub: they depend only on this module, and the hub
 * re-exports the public names for external consumers.
 */
import * as THREE from "three";
import type { WebGPURenderer } from "three/webgpu";
import type { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { LightRig } from "./lighting";
import type { ComposerHandle } from "./postprocessing";
import type { GridHandle } from "./grid";

/** The contact-shadow ground lives here so the AO input pass, whose camera
 *  disables this layer, never samples it as an occluder. The main camera enables
 *  this layer so the ground still renders into the beauty pass. */
export const FLOOR_LAYER = 1;

/** The work-plane grid lives here, alone, so it renders in its own pass (the
 *  grid camera sees ONLY this layer) and never enters the TRAA-jittered scene
 *  pass — temporal AA dissolves its fine minor lines. Composited back over the
 *  beauty with a model-depth occlusion test (see buildComposer). */
export const GRID_LAYER = 2;

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

/** Right-click pick callback registry, kept off React state. */
export interface PickState {
  onPick: ((p: PickEvent) => void) | null;
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
