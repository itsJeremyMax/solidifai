import * as THREE from "three";

/** Camera distance so a box of `maxDim` fits a `fovDeg`-degree perspective, with padding. */
export function fitDistance(maxDim: number, fovDeg: number): number {
  const fov = (fovDeg * Math.PI) / 180;
  return Math.max((maxDim / 2 / Math.tan(fov / 2)) * 1.7, maxDim * 0.6);
}

/** Position `camera` on the canonical front-top-right iso corner, framed to `box`. */
export function placeIsoCamera(camera: THREE.PerspectiveCamera, box: THREE.Box3): void {
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  const dist = fitDistance(maxDim, camera.fov);
  const dir = new THREE.Vector3(1, 1, 1).normalize(); // iso
  camera.position.copy(center).addScaledVector(dir, dist);
  camera.near = Math.max(dist * 0.1, 0.01);
  camera.far = dist + maxDim * 8;
  camera.lookAt(center);
  camera.updateProjectionMatrix();
}
