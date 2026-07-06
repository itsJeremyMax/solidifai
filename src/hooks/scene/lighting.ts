/**
 * The viewport light rig: hemisphere + ambient fill, a shadow-casting key
 * directional, and a cool rim. Intensities are tuned to sit ON TOP of the IBL
 * environment (which now provides most of the ambient fill), so hemi/ambient are
 * lower than a no-IBL rig would use.
 */
import * as THREE from "three";

export interface LightRig {
  /** The shadow-casting key light (exposed for debugging / future tuning). */
  key: THREE.DirectionalLight;
  /** Scale the shadow camera (ortho bounds, near/far, key-light distance) to the model. */
  setShadowExtent: (modelSize: number) => void;
  /**
   * Toggle soft (PCF, blurred) contact shadows vs hard shadows. Soft uses the
   * key light's `shadow.radius` blur; hard sets radius 0 for a crisp edge. The
   * renderer's shadow-map type stays PCFSoftShadowMap (set once in useThreeScene);
   * radius 0 there reads as a hard edge, so no renderer-level reconfigure is needed.
   */
  setSoftShadows: (soft: boolean) => void;
  dispose: () => void;
}

export function buildLightRig(scene: THREE.Scene): LightRig {
  const hemi = new THREE.HemisphereLight(0xeef3fb, 0x20242d, 0.5);
  scene.add(hemi);

  const ambient = new THREE.AmbientLight(0xffffff, 0.12);
  scene.add(ambient);

  // Warm key vs. cool rim/IBL — the temperature contrast gives the part premium,
  // three-dimensional depth instead of flat white light.
  const key = new THREE.DirectionalLight(0xfff4e8, 1.6);
  key.position.set(80, 140, 60);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.near = 1;
  key.shadow.camera.far = 800;
  key.shadow.radius = 8; // big-softbox contact shadow
  const c = key.shadow.camera as THREE.OrthographicCamera;
  c.left = -200;
  c.right = 200;
  c.top = 200;
  c.bottom = -200;
  c.updateProjectionMatrix();
  scene.add(key);

  // Cool rim, strong enough to separate the part's silhouette from the dark
  // graphite background (the lower edges otherwise melt into it).
  const rim = new THREE.DirectionalLight(0x9cb4ff, 0.6);
  rim.position.set(-100, 40, -80);
  scene.add(rim);

  return {
    key,
    setShadowExtent: (modelSize) => {
      // Keep the key light's DIRECTION (shading is distance-independent for a
      // directional light) but move it to a model-proportional distance so the
      // shadow camera can frame the part, then size the ortho frustum + near/far
      // to the model. Fixes the hardcoded ±200/far-800 assumption.
      const dir = new THREE.Vector3(80, 140, 60).normalize();
      key.position.copy(dir.multiplyScalar(modelSize * 3));
      const half = modelSize * 1.5;
      const cam = key.shadow.camera as THREE.OrthographicCamera;
      cam.left = -half;
      cam.right = half;
      cam.top = half;
      cam.bottom = -half;
      cam.near = modelSize * 1;
      cam.far = modelSize * 6;
      cam.updateProjectionMatrix();
    },
    setSoftShadows: (soft) => {
      // 8px softbox blur (the build default) when soft; 0 = crisp/hard edge.
      key.shadow.radius = soft ? 8 : 0;
    },
    dispose: () => {
      scene.remove(hemi, ambient, key, rim);
      hemi.dispose();
      ambient.dispose();
      key.dispose();
      rim.dispose();
    },
  };
}
