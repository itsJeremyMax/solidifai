/**
 * Build a three.js material from an engine-resolved {@link Appearance}. This is
 * the ONLY place appearance → three material mapping lives. Base colors are
 * LINEAR RGB (set via LinearSRGBColorSpace so they are not double-converted).
 */
import * as THREE from "three";
import type { Appearance } from "../../lib/artifacts";

/** Matte light-gray PLA — used when an object has no appearance (schema-1). */
export const DEFAULT_APPEARANCE: Appearance = {
  material: "pla",
  baseColor: [0.52, 0.54, 0.57],
  metalness: 0.0,
  roughness: 0.62,
  clearcoat: 0.0,
  clearcoatRoughness: 0.0,
};

export function materialFromAppearance(
  appearance: Appearance | undefined,
): THREE.MeshPhysicalMaterial {
  const a = appearance ?? DEFAULT_APPEARANCE;
  const [r, g, b] = a.baseColor;
  const color = new THREE.Color().setRGB(r, g, b, THREE.LinearSRGBColorSpace);
  const material = new THREE.MeshPhysicalMaterial({
    color,
    metalness: a.metalness,
    roughness: a.roughness,
    clearcoat: a.clearcoat,
    clearcoatRoughness: a.clearcoatRoughness,
  });
  // Ghost imported references: an opacity < 1 makes the part translucent. STL
  // references are open surfaces, so render both sides, and skip depth writes so
  // a ghost never z-fights its own back faces or hides the part behind it.
  if (typeof a.opacity === "number" && a.opacity < 1) {
    material.transparent = true;
    material.opacity = a.opacity;
    material.side = THREE.DoubleSide;
    material.depthWrite = false;
  }
  return material;
}
