import * as THREE from "three";

/**
 * Convert a three.js WORLD-space point (mm, glTF Y-up, with the model's
 * ground-drop applied to modelGroup) to build123d's native Z-up mm frame, which
 * is what the engine's `feature_at` expects.
 *
 * (1) subtract modelGroup.position to undo the ground-drop/placement → GLB-local
 * (Y-up) point; (2) invert the export's Z-up→Y-up rotation. build123d/glTF maps
 * build123d (X,Y,Z) → glTF (X, Z, -Y), so the inverse is build123d (x, -z, y).
 */
export function glbWorldToEngineMm(
  worldPoint: THREE.Vector3,
  modelGroup: THREE.Object3D,
): [number, number, number] {
  const local = worldPoint.clone().sub(modelGroup.position);
  return [local.x, -local.z, local.y];
}

/** Inverse: build123d Z-up mm → three.js world point (for framing/markers). */
export function engineMmToGlbWorld(
  mm: [number, number, number],
  modelGroup: THREE.Object3D,
): THREE.Vector3 {
  const [x, y, z] = mm;
  // Inverse of (x,-z,y): glTF (x, z, -y) from build123d (x,y,z).
  const local = new THREE.Vector3(x, z, -y);
  return local.add(modelGroup.position);
}
