/**
 * Infinite work-plane grid on the y=0 floor — the CAD "stage" the part sits on.
 *
 * A single transparent plane with a derivative-based line shader (crisp at any
 * zoom, no texture/moire), drawing two scales: faint cool-gray minor cells and a
 * cobalt accent major every section. The grid fades to nothing with distance from
 * the origin so it reads as a studio stage that focuses the part, not wallpaper.
 * Cell/section/fade all scale to the model so it looks right at any part size.
 *
 * Lives alone on GRID_LAYER and renders in its own pass (see buildComposer): it
 * is kept OUT of the TRAA-jittered scene pass, whose temporal averaging was
 * dissolving the fine minor lines. Because nothing else shares this pass there is no coplanar z-fight, so it writes depth normally.
 * That depth feeds the model-occlusion test that composites the grid back under the part.
 */
import * as THREE from "three";
import { MeshBasicNodeMaterial } from "three/webgpu";
import {
  positionWorld,
  float,
  abs,
  fract,
  fwidth,
  min,
  max,
  length,
  smoothstep,
  mix,
  uniform,
} from "three/tsl";

export interface GridHandle {
  /** Scale the grid (cell/section/extent) to the model's largest dimension. */
  setScale: (modelSize: number) => void;
  /** Show/hide the work-plane grid (the context-menu "Toggle grid" action). */
  setVisible: (v: boolean) => void;
  /** Move the grid onto `layer` exclusively, so it renders only in the dedicated
   *  (un-jittered) grid pass and stays out of the TRAA'd scene pass. */
  setLayer: (layer: number) => void;
  dispose: () => void;
}

export function buildGrid(scene: THREE.Scene): GridHandle {
  const uCell = uniform(0.1);
  const uSection = uniform(0.5);
  const uFade = uniform(6.0);
  const uCellColor = uniform(new THREE.Color(0x5e6a80)); // cool slate minor lines
  const uSectionColor = uniform(new THREE.Color(0x2b6cff)); // cobalt accent major lines

  // Anti-aliased line coverage via screen-space derivatives (matches the old GLSL):
  //   vec2 g = abs(fract(coord - 0.5) - 0.5) / fwidth(coord);
  //   return 1.0 - min(min(g.x, g.y), 1.0);
  const p = positionWorld.xz.toVar();

  const coordMinor = p.div(uCell);
  const gMinor = abs(fract(coordMinor.sub(0.5)).sub(0.5)).div(fwidth(coordMinor));
  const minorLine = float(1.0).sub(min(min(gMinor.x, gMinor.y), float(1.0)));

  const coordMajor = p.div(uSection);
  const gMajor = abs(fract(coordMajor.sub(0.5)).sub(0.5)).div(fwidth(coordMajor));
  const majorLine = float(1.0).sub(min(min(gMajor.x, gMajor.y), float(1.0)));

  const fade = float(1.0).sub(smoothstep(uFade.mul(0.2), uFade, length(p)));
  const gridColor = mix(uCellColor, uSectionColor, majorLine);
  const gridAlpha = max(minorLine.mul(0.42), majorLine.mul(0.5)).mul(fade);

  const material = new MeshBasicNodeMaterial();
  material.transparent = true;
  // Alone in its own pass: write depth so the plane's z feeds the model-occlusion
  // composite (no coplanar geometry here to z-fight).
  material.depthWrite = true;
  material.side = THREE.DoubleSide;
  material.colorNode = gridColor;
  material.opacityNode = gridAlpha;

  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
  mesh.rotation.x = -Math.PI / 2; // lie flat on the XZ plane at y=0
  scene.add(mesh);

  return {
    setScale: (modelSize) => {
      uCell.value = modelSize * 0.1; // ~10 minor cells across the part
      uSection.value = modelSize * 0.5; // major line every half-part
      uFade.value = modelSize * 6; // fade out by ~6× the part size
      const span = modelSize * 16; // plane large enough to fully contain the fade
      mesh.scale.set(span, span, 1);
    },
    setVisible: (v) => {
      mesh.visible = v;
    },
    setLayer: (layer) => {
      mesh.layers.set(layer);
    },
    dispose: () => {
      scene.remove(mesh);
      mesh.geometry.dispose();
      material.dispose();
    },
  };
}
