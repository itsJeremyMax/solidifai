/**
 * useShadeBall — offscreen WebGPU thumbnail renderer for material shade balls.
 *
 * ONE module-level WebGPURenderer + scene + sphere is shared across every card.
 * Each material is rendered to a data URL and cached by its appearance hash, so a
 * given base/color/finish only ever renders once no matter how many cards (or the
 * editor preview) show it. The hook returns the cached URL synchronously when it
 * exists, or null while the (async) render is in flight.
 *
 * The scene mirrors the live viewport (src/hooks/scene/*) so thumbnails read the
 * same as the part on the stage:
 *   • IBL: RoomEnvironment through PMREMGenerator at environmentIntensity 0.5
 *     (environment.ts).
 *   • Lights: the same hemi + ambient + warm key + cool rim character (lighting.ts),
 *     minus shadows (a lone sphere on a transparent background casts none).
 *   • Material: MeshPhysicalMaterial with the base color set as LINEAR RGB via
 *     LinearSRGBColorSpace, exactly like materialFromAppearance (scene/materials.ts),
 *     so colors are not double-converted.
 *   • Tone map: NeutralToneMapping, as in useThreeScene.
 *
 * Capture: a WebGPU canvas does not reliably preserve its drawing buffer for
 * `domElement.toDataURL()` after a render, so instead of reading the canvas we
 * render into a RenderTarget and read the pixels back. The renderer applies its
 * tone-map + sRGB output transform only when drawing to its OUTPUT target (see
 * Renderer.isOutputTarget / currentColorSpace in three), so we register the
 * target via `setOutputRenderTarget` before rendering. That makes the read-back
 * bytes already tone-mapped and sRGB-encoded (display-ready), matching the
 * canvas. We then blit them into a 2D canvas and `toDataURL` that. The renderer
 * is alpha:true with a transparent clear, so the PNG has a transparent
 * background and each card composites it over its own surface.
 */
import { useEffect, useState } from "react";
import * as THREE from "three/webgpu";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { appearanceFor, appearanceHash } from "../lib/materialAppearance";
import type { Material } from "../lib/materials";

/** Device-px square render size; cards downscale via CSS for crispness. */
const SIZE = 192;

/** One offscreen renderer + scene + cache, shared across every card. */
const cache = new Map<string, string>();

/** Bounded cache: the live color picker mints a new PNG per value, so an unbounded
 *  Map would grow without limit. Evict oldest (Map keeps insertion order). */
const CACHE_CAP = 128;
function cachePut(key: string, url: string): void {
  if (cache.size >= CACHE_CAP) {
    const oldest = cache.keys().next().value;
    if (oldest !== undefined) cache.delete(oldest);
  }
  cache.set(key, url);
}

interface ShadeBallCtx {
  renderer: THREE.WebGPURenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  mesh: THREE.Mesh;
  target: THREE.RenderTarget;
  /** Reused 2D canvas the read-back pixels are blitted into for toDataURL. */
  canvas: HTMLCanvasElement;
  /** Serializes renders so concurrent cards don't fight over the single mesh. */
  ready: Promise<void>;
}

let ctx: ShadeBallCtx | null = null;

function ensureCtx(): ShadeBallCtx {
  if (ctx) return ctx;

  const renderer = new THREE.WebGPURenderer({ antialias: true, alpha: true });
  renderer.setSize(SIZE, SIZE);
  renderer.setClearColor(0x000000, 0); // transparent background; cards composite over their own surface
  renderer.toneMapping = THREE.NeutralToneMapping; // matches the viewport (useThreeScene)

  const scene = new THREE.Scene();

  // ── light rig: same temperature contrast as scene/lighting.ts (no shadows) ──
  const hemi = new THREE.HemisphereLight(0xeef3fb, 0x20242d, 0.5);
  scene.add(hemi);
  const ambient = new THREE.AmbientLight(0xffffff, 0.12);
  scene.add(ambient);
  // Warm key vs. cool rim/IBL gives the ball premium, three-dimensional depth.
  const key = new THREE.DirectionalLight(0xfff4e8, 1.6);
  key.position.set(2, 3, 1.5); // up/front/right, mirroring lighting.ts's (80,140,60) direction
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x9cb4ff, 0.6);
  rim.position.set(-2.5, 1, -2); // mirrors lighting.ts's (-100,40,-80) rim direction
  scene.add(rim);

  const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 100);
  camera.position.set(0, 0, 4.2);
  camera.lookAt(0, 0, 0);

  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(1, 64, 48),
    new THREE.MeshPhysicalMaterial(),
  );
  scene.add(mesh);

  // Read-back target. Registered as the renderer's OUTPUT target before each
  // render so the tone-map + sRGB output transform is applied into it (the
  // renderer skips that transform for non-output targets).
  const target = new THREE.RenderTarget(SIZE, SIZE, { depthBuffer: true });

  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;

  const built: ShadeBallCtx = {
    renderer,
    scene,
    camera,
    mesh,
    target,
    canvas,
    // IBL: RoomEnvironment via PMREM, dialed down — same as scene/environment.ts.
    // Attached after init: PMREMGenerator.fromScene throws on an uninitialized
    // backend (always lost on the WebGL fallback path, e.g. under Rosetta).
    ready: renderer.init().then(() => {
      const pmrem = new THREE.PMREMGenerator(renderer);
      scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
      scene.environmentIntensity = 0.5;
    }),
  };
  ctx = built;
  return built;
}

/** Serialize renders: a chain so concurrent callers reuse the single mesh safely. */
let queue: Promise<void> = Promise.resolve();

async function renderThumbnail(m: Material): Promise<string> {
  const key = appearanceHash(m);
  const hit = cache.get(key);
  if (hit) return hit;

  const c = ensureCtx();

  // Chain onto the queue so two cards never mutate the shared mesh mid-render.
  const run = queue.then(async () => {
    // A later card may have rendered this exact appearance while we waited.
    const already = cache.get(key);
    if (already) return already;

    await c.ready;

    const a = appearanceFor(m);
    const mat = c.mesh.material as THREE.MeshPhysicalMaterial;
    // Base color is LINEAR RGB — set via LinearSRGBColorSpace so it is not
    // double-converted (exactly as scene/materials.ts does for the viewport).
    mat.color.setRGB(a.baseColor[0], a.baseColor[1], a.baseColor[2], THREE.LinearSRGBColorSpace);
    mat.metalness = a.metalness;
    mat.roughness = a.roughness;
    mat.clearcoat = a.clearcoat;
    mat.clearcoatRoughness = a.clearcoatRoughness;
    mat.needsUpdate = true;

    // Render into the target AS the output target, so tone-map + sRGB are baked
    // into the read-back pixels, then restore screen output.
    c.renderer.setOutputRenderTarget(c.target);
    await c.renderer.renderAsync(c.scene, c.camera);
    c.renderer.setOutputRenderTarget(null);

    const pixels = await c.renderer.readRenderTargetPixelsAsync(c.target, 0, 0, SIZE, SIZE);
    const url = pixelsToDataURL(c.canvas, pixels);
    cachePut(key, url);
    return url;
  });

  // Keep the queue alive (and swallow this run's rejection so one failure does
  // not poison every later render).
  queue = run.then(() => undefined).catch(() => undefined);
  return run;
}

/** Blit RGBA8 read-back bytes into the 2D canvas and return a PNG data URL. */
function pixelsToDataURL(canvas: HTMLCanvasElement, pixels: ArrayLike<number>): string {
  const c2d = canvas.getContext("2d");
  if (!c2d) return "";
  const data = new Uint8ClampedArray(SIZE * SIZE * 4);
  data.set(pixels as Uint8Array);
  c2d.putImageData(new ImageData(data, SIZE, SIZE), 0, 0);
  return canvas.toDataURL("image/png");
}

/**
 * Returns a data-URL thumbnail for the material, or null while it renders.
 * Re-renders only when the appearance hash changes (id/label do not affect the
 * render, so renaming a material reuses the cached image).
 */
export function useShadeBall(m: Material): string | null {
  const hash = appearanceHash(m);
  const [url, setUrl] = useState<string | null>(() => cache.get(hash) ?? null);

  useEffect(() => {
    let live = true;
    const cached = cache.get(hash);
    if (cached) {
      setUrl(cached);
      return;
    }
    setUrl(null);
    renderThumbnail(m)
      .then((u) => {
        if (live) setUrl(u);
      })
      .catch(() => {
        /* leave url null; MaterialCard shows its tinted-sphere fallback */
      });
    return () => {
      live = false;
    };
    // Key on the appearance hash only: a rename (same appearance) must reuse the
    // cached image, so `m` is intentionally omitted from the deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hash]);

  return url;
}
