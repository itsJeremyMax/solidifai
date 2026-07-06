/**
 * Client-side exploded view: spread parts outward from the assembly center by a
 * uniform scale (homothety), then re-seat the whole set so the lowest part sits
 * exactly on the grid. Because the offset is proportional to each part's
 * displacement from the center (not normalized), a 3D assembly (e.g. a PC case)
 * explodes radially in all directions, while a stacked enclosure (Base+Lid),
 * whose parts differ mainly in height, separates almost purely vertically with no
 * sideways drift. The base stays planted on the grid and nothing ever goes below
 * it. A part at the center does not move. Pure viewport transform, like camera
 * orbit (no engine round-trip).
 */
import * as THREE from "three";

/** Homothety coefficient at factor=100 (each part moves out by this * its
 *  distance from the assembly center). Tunable: higher = more dramatic spread. */
const EXPAND = 1.5;

/** Per-part assembled basis, captured once per build at factor 0. */
export interface ExplodeBasis {
  parts: { basePosition: THREE.Vector3; displacement: THREE.Vector3; minY: number }[];
  /** Lowest world Y of the assembled model = the grid contact plane. */
  floorY: number;
}

/**
 * Capture each subtree's assembled basis. Precondition: the caller must have
 * called `updateMatrixWorld(true)` on the scene root first, so `setFromObject`
 * reads fresh world matrices. Call at factor 0 (assembled).
 */
export function captureExplodeBasis(subtrees: THREE.Object3D[]): ExplodeBasis {
  const union = new THREE.Box3();
  const measured = subtrees.map((s) => {
    const box = new THREE.Box3().setFromObject(s);
    const empty = box.isEmpty();
    const center = empty
      ? s.getWorldPosition(new THREE.Vector3())
      : box.getCenter(new THREE.Vector3());
    const minY = empty ? center.y : box.min.y;
    if (!empty) union.union(box);
    return { basePosition: s.position.clone(), center, minY };
  });
  const assemblyCenter = union.isEmpty()
    ? new THREE.Vector3()
    : union.getCenter(new THREE.Vector3());
  const floorY = union.isEmpty() ? 0 : union.min.y;
  const height = union.isEmpty() ? 1 : Math.max(union.max.y - union.min.y, 1);
  const floorEps = 1e-3 * height;
  // Horizontal explosion origin = centroid of the parts resting on the grid (the
  // "base"). A single off-center base becomes its own center, so it never drifts
  // horizontally; symmetric feet / a central tray average to the assembly center,
  // so symmetric assemblies still spread evenly. Vertical origin stays the
  // assembly center (the floor re-seat in applyExplode grounds the result).
  let fx = 0;
  let fz = 0;
  let n = 0;
  measured.forEach((m) => {
    if (m.minY <= floorY + floorEps) {
      fx += m.center.x;
      fz += m.center.z;
      n += 1;
    }
  });
  const origin = new THREE.Vector3(
    n > 0 ? fx / n : assemblyCenter.x,
    assemblyCenter.y,
    n > 0 ? fz / n : assemblyCenter.z,
  );
  const parts = measured.map((m) => ({
    basePosition: m.basePosition,
    displacement: m.center.clone().sub(origin),
    minY: m.minY,
  }));
  return { parts, floorY };
}

/**
 * Apply an explode `factor` (0..100; values above 100 scale proportionally).
 * Offset each part by `displacement * (factor/100 * EXPAND)` (radial from the
 * assembly center), then lift the whole set uniformly so the lowest part's bottom
 * sits exactly on the grid (`floorY`). Idempotent: re-applies from `basePosition`.
 */
export function applyExplode(
  subtrees: THREE.Object3D[],
  basis: ExplodeBasis,
  factor: number,
): void {
  const scale = (Math.max(0, factor) / 100) * EXPAND;

  // Re-seat: keep the lowest exploded part bottom glued to the grid plane.
  let lowest = Infinity;
  basis.parts.forEach((p) => {
    lowest = Math.min(lowest, p.minY + p.displacement.y * scale);
  });
  const lift = Number.isFinite(lowest) ? basis.floorY - lowest : 0;

  subtrees.forEach((s, i) => {
    const p = basis.parts[i];
    if (!p) return;
    const worldDelta = p.displacement.clone().multiplyScalar(scale);
    worldDelta.y += lift;
    const parent = s.parent;
    if (!parent) {
      s.position.copy(p.basePosition).add(worldDelta);
      return;
    }
    // Convert the world-space delta to the subtree's parent-local frame so it is
    // correct under any parent transform (transform two points, subtract to drop
    // translation).
    parent.updateWorldMatrix(true, false);
    const inv = new THREE.Matrix4().copy(parent.matrixWorld).invert();
    const a = new THREE.Vector3().applyMatrix4(inv);
    const b = worldDelta.clone().applyMatrix4(inv);
    s.position.copy(p.basePosition).add(b.sub(a));
  });
}
