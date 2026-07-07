import * as THREE from "three";

/** Dispose all geometries/materials/textures under `object`. */
export function disposeObject(object: THREE.Object3D): void {
  object.traverse((node) => {
    const mesh = node as THREE.Mesh;
    if (mesh.isMesh) {
      mesh.geometry?.dispose();
      const mat = mesh.material;
      if (Array.isArray(mat)) mat.forEach((m) => disposeMaterial(m));
      else if (mat) disposeMaterial(mat);
    }
  });
}

export function disposeMaterial(mat: THREE.Material): void {
  // Free any textures the material references before disposing it.
  for (const value of Object.values(mat as unknown as Record<string, unknown>)) {
    if (value && (value as THREE.Texture).isTexture) {
      (value as THREE.Texture).dispose();
    }
  }
  mat.dispose();
}
