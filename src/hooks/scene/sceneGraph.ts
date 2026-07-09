import * as THREE from "three";
import type { ModelObject } from "../../lib/artifacts";
import { idMatchesBase } from "../../lib/assemblyTree";
import type { SceneRefs } from "./types";
import { refreshClipPlanes } from "./camera";

/**
 * The per-object subtrees of a loaded GLB, in show()/registry order. The
 * exporter nests all shown objects under one wrapper node whose children are the
 * per-object nodes; that wrapper is the shallowest node with exactly `n`
 * children (BFS). For n ≤ 1 the scene itself is returned as the single subtree.
 * Verified against build123d 0.10 export_gltf for n = 1, 2, 3.
 */
export function objectSubtrees(scene: THREE.Object3D, n: number): THREE.Object3D[] {
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
 * Indices of every subtree the selection `id` resolves to: the exact leaf, all
 * descendant leaves when `id` is an assembly-node prefix, and every occurrence
 * sibling of an instanced part (`wheel` -> `wheel_2`, `wheel_3`). See
 * {@link idMatchesBase} for the guards. Selecting a group or an instanced part
 * thus highlights every child mesh it stands for.
 */
export function subtreeIndicesForId(
  objects: ModelObject[] | undefined,
  id: string | null,
): number[] {
  if (!objects || id == null) return [];
  const out: number[] = [];
  objects.forEach((o, i) => {
    if (idMatchesBase(o.id, id)) out.push(i);
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

/**
 * Frame the camera so the model fills the view, then re-center the orbit target
 * + ground plane on it. Preserves the current viewing direction.
 *
 * Caches the model's largest dimension on `handle.frameMaxDim` so the render
 * loop can re-bracket near/far against the live zoom (see refreshClipPlanes) and
 * callers (GTAO / grid / ground sizing) can scale to the part without a second
 * `setFromObject` traversal. No-op when the model has no renderable geometry.
 */
export function frameToObject(handle: SceneRefs): void {
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
