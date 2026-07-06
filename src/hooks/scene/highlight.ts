/**
 * Selection highlight rig — gently tints the selected subtree's meshes by
 * cloning their materials and lifting `emissive` toward cobalt, restoring the
 * originals on clear. No composer pass, so it can't perturb the GTAO/SMAA
 * pipeline (the studio render look is sensitive — see the render-look notes).
 * If the tint reads too weak/strong, tune the constants; OutlinePass is the heavier alternative.
 */
import * as THREE from "three";

const HIGHLIGHT_EMISSIVE = new THREE.Color("#2b6cff");
const HIGHLIGHT_INTENSITY = 0.22;

export interface SelectionHighlight {
  /** Highlight exactly this subtree (clears any previous selection first). */
  apply(subtree: THREE.Object3D): void;
  /** Highlight all of these subtrees at once (clears any previous selection
   *  first, then tints every one). Used when a selected assembly node resolves
   *  to several descendant subtrees. Empty array == clear. */
  applyMany(subtrees: THREE.Object3D[]): void;
  /** Remove all highlighting, restoring original materials. */
  clear(): void;
}

export function createSelectionHighlight(): SelectionHighlight {
  const swapped: { mesh: THREE.Mesh; original: THREE.Material | THREE.Material[] }[] = [];

  function clear() {
    for (const { mesh, original } of swapped) {
      const clone = mesh.material;
      mesh.material = original;
      if (Array.isArray(clone)) clone.forEach((m) => m.dispose());
      else (clone as THREE.Material).dispose();
    }
    swapped.length = 0;
  }

  // Tint one subtree's meshes WITHOUT clearing first; callers clear once up front.
  function tint(subtree: THREE.Object3D) {
    subtree.traverse((node) => {
      const mesh = node as THREE.Mesh;
      if (!mesh.isMesh) return;
      const original = mesh.material;
      const src = (Array.isArray(original) ? original[0] : original) as THREE.Material;
      const cloned = src.clone() as THREE.MeshStandardMaterial;
      if ("emissive" in cloned) {
        cloned.emissive = HIGHLIGHT_EMISSIVE.clone();
        cloned.emissiveIntensity = HIGHLIGHT_INTENSITY;
      }
      swapped.push({ mesh, original });
      mesh.material = cloned;
    });
  }

  function apply(subtree: THREE.Object3D) {
    clear();
    tint(subtree);
  }

  function applyMany(subtrees: THREE.Object3D[]) {
    clear();
    for (const subtree of subtrees) tint(subtree);
  }

  return { apply, applyMany, clear };
}
