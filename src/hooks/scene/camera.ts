/**
 * Camera depth-slab control.
 *
 * The near/far planes are bracketed tightly around the framed scene (the part +
 * its work-plane grid) to keep depth precision where the geometry actually is.
 * A wide span starves the depth buffer: on very thin parts the slab's own
 * top/bottom faces and engraved labels z-fight and flicker on camera motion. A
 * ~1:40 range distributes precision where it's needed.
 *
 * Because the slab is tight it must follow the LIVE orbit distance, not the
 * distance captured when the part was framed. Freezing it let a zoom-out dolly
 * push the model past a fixed far plane, clipping it and revealing the black
 * background as a "wall" creeping over the part. Recompute every frame instead.
 */
import type * as THREE from "three";

/** Far plane reaches this many model-sizes past the orbit pivot. */
const FAR_REACH = 8;
/** Near plane sits at this fraction of the current pivot distance. */
const NEAR_FRACTION = 0.1;

/**
 * Re-bracket `camera`'s near/far around a model of size `maxDim` centered on
 * `target`, from the camera's current distance to that pivot. Cheap enough to
 * call every frame; only rebuilds the projection matrix when a plane moved.
 */
export function refreshClipPlanes(
  camera: THREE.PerspectiveCamera,
  target: THREE.Vector3,
  maxDim: number,
): void {
  const dist = camera.position.distanceTo(target);
  const near = Math.max(dist * NEAR_FRACTION, 0.01);
  const far = dist + maxDim * FAR_REACH;
  if (near === camera.near && far === camera.far) return;
  camera.near = near;
  camera.far = far;
  camera.updateProjectionMatrix();
}
