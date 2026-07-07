import * as THREE from "three";
import { FLOOR_LAYER, type SceneRefs } from "./types";
import { placeIsoCamera } from "./isoFit";
import { isWebGLReadback, packReadbackRows } from "./readback";

/**
 * Render a normalized iso snapshot of the current model to a PNG blob, framed
 * fresh on a throwaway camera + render target so the caller's live view (camera,
 * controls, post-processing) is never disturbed. Includes the contact-shadow
 * ground but not the work-plane grid; the transparent clear yields a PNG with
 * alpha around the part. Resolves `null` when there's no model, or on any GPU
 * failure (the caller falls back to a placeholder).
 */
export async function captureThumbnail(
  handle: SceneRefs,
  w: number,
  h: number,
): Promise<Blob | null> {
  if (handle.modelGroup.children.length === 0) return null;
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
    const buf = (await handle.renderer.readRenderTargetPixelsAsync(rt, 0, 0, pw, ph)) as Uint8Array;
    return await pngFromPixels(buf, pw, ph, isWebGLReadback(handle.renderer));
  } catch (e) {
    console.warn("thumbnail capture failed", e);
    return null;
  } finally {
    handle.renderer.setRenderTarget(prev);
    rt.dispose();
    handle.requestRender(); // repaint the live view (which we never moved)
  }
}

/**
 * Encode a raw RGBA byte buffer (one `w`×`h` frame, 4 bytes/pixel) to a PNG blob.
 *
 * `flipY` must be true on the WebGL fallback backend, whose readback rows come
 * back bottom-up; WebGPU readback is already top-down (see scene/readback.ts).
 * Resolves `null` if a canvas isn't available or PNG encoding fails, so the
 * capture path always degrades to a placeholder.
 */
export function pngFromPixels(
  buf: Uint8Array,
  w: number,
  h: number,
  flipY: boolean,
): Promise<Blob | null> {
  return new Promise((resolve) => {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) return resolve(null);

      const out = ctx.createImageData(w, h);
      out.data.set(packReadbackRows(buf, w, h, flipY));
      ctx.putImageData(out, 0, 0);
      canvas.toBlob((blob) => resolve(blob), "image/png");
    } catch {
      resolve(null);
    }
  });
}
