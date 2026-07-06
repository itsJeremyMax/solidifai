/**
 * Image-based lighting via three's procedural RoomEnvironment (neutral studio,
 * zero asset weight). Prefiltered through PMREMGenerator and assigned to
 * scene.environment so metals have something to reflect. scene.background is
 * left untouched — the CSS graphite gradient shows through the transparent canvas.
 *
 * Swappable: to use an HDRI later, replace the fromScene(...) source here; no
 * caller changes.
 */
import * as THREE from "three";
// PMREMGenerator from three/webgpu accepts the WebGPURenderer (the bare-"three"
// export's PMREMGenerator is typed for the legacy renderer only). RoomEnvironment stays an addon import.
import { PMREMGenerator, type WebGPURenderer } from "three/webgpu";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export interface EnvHandle {
  dispose: () => void;
}

export function setupEnvironment(scene: THREE.Scene, renderer: WebGPURenderer): EnvHandle {
  const pmrem = new PMREMGenerator(renderer);
  const envTexture = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environment = envTexture;
  // Tonal restraint: RoomEnvironment is a bright studio; at full strength it
  // over-lights diffuse surfaces and washes a light material to flat white. Dial
  // the IBL contribution down so the part reads its own neutral albedo (with
  // soft reflections for material richness) — the "machined part on a graphite
  // stage" look, not a white blob.
  scene.environmentIntensity = 0.5;
  return {
    dispose: () => {
      scene.environment = null;
      scene.environmentIntensity = 1;
      envTexture.dispose();
      pmrem.dispose();
    },
  };
}
