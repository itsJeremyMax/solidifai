import { describe, it, expect } from "vitest";
import * as THREE from "three";
import { refreshClipPlanes } from "./camera";

// Place a camera `dist` away from `target` along an iso-ish direction, the way
// OrbitControls leaves it after a dolly.
function cameraAt(dist: number, target = new THREE.Vector3()): THREE.PerspectiveCamera {
  const cam = new THREE.PerspectiveCamera(38, 1, 0.1, 5000);
  const dir = new THREE.Vector3(1, 0.8, 1).normalize();
  cam.position.copy(target).addScaledVector(dir, dist);
  return cam;
}

describe("refreshClipPlanes (live depth-slab bracketing)", () => {
  const maxDim = 0.09; // a small part, like the printed pot

  const r = maxDim / 2; // bounding radius around the pivot

  // The reported bug: the far plane was frozen at frame time, so zooming out
  // pushed the part's back face past it (clipped → black). The far face must
  // stay inside the frustum at every distance, especially far out.
  it.each([0.6, 1, 2.5, 5, 12, 50].map((m) => m * 0.09))(
    "never clips the back face at dist=%f",
    (dist) => {
      const target = new THREE.Vector3();
      const cam = cameraAt(dist, target);
      refreshClipPlanes(cam, target, maxDim);
      expect(cam.near).toBeGreaterThan(0);
      expect(cam.far).toBeGreaterThanOrEqual(dist + r);
    },
  );

  // From the framing distance (~2.5x maxDim) outward the front face is also
  // inside. Closer than that the absolute 0.01 near floor can bite on a tiny
  // part, but that's a pre-existing macro-zoom-in tradeoff, not this bug.
  it.each([2.5, 5, 12, 50].map((m) => m * 0.09))(
    "never clips the front face once framed at dist=%f",
    (dist) => {
      const target = new THREE.Vector3();
      const cam = cameraAt(dist, target);
      refreshClipPlanes(cam, target, maxDim);
      expect(cam.near).toBeLessThanOrEqual(dist - r);
    },
  );

  it("tracks the live distance: far grows when you dolly out", () => {
    const target = new THREE.Vector3();
    const near = cameraAt(maxDim * 2, target);
    const out = cameraAt(maxDim * 40, target);
    refreshClipPlanes(near, target, maxDim);
    refreshClipPlanes(out, target, maxDim);
    expect(out.far).toBeGreaterThan(near.far);
    expect(out.near).toBeGreaterThan(near.near);
  });

  it("keeps a bounded near:far ratio so the depth buffer never starves", () => {
    // The tight slab is what stops thin-part z-fighting; verify it stays tight
    // across the whole zoom range rather than blowing out to a 1:10000 span.
    const target = new THREE.Vector3();
    for (const dist of [maxDim * 0.6, maxDim * 5, maxDim * 50]) {
      const cam = cameraAt(dist, target);
      refreshClipPlanes(cam, target, maxDim);
      expect(cam.far / cam.near).toBeLessThan(200);
    }
  });

  it("does not touch the projection matrix when the planes are unchanged", () => {
    const target = new THREE.Vector3();
    const cam = cameraAt(maxDim * 3, target);
    refreshClipPlanes(cam, target, maxDim);
    const before = cam.projectionMatrix.elements.slice();
    refreshClipPlanes(cam, target, maxDim); // same pose → no-op
    expect(Array.from(cam.projectionMatrix.elements)).toEqual(Array.from(before));
  });
});
