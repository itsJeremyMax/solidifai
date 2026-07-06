/**
 * Preview post-processing — node pipeline on WebGPURenderer.
 *
 * Graph: pass(scene,camera) → AO multiply → TRAA → grid overlay → output. Scene pass provides color + velocity for TRAA; a model-only AO pass (aoCamera disables FLOOR_LAYER) feeds temporal GTAO denoised by TRAA. The grid renders in its own un-jittered pass, composited after TRAA.
 * Tone map + sRGB are applied by the RenderPipeline's output transform (replaces the legacy composer-based output
 * and anti-aliasing passes).
 */
import * as THREE from "three";
import { RenderPipeline, type WebGPURenderer } from "three/webgpu";
import {
  pass,
  mrt,
  output,
  normalView,
  velocity,
  vec3,
  vec4,
  mix,
  float,
  step,
  uniform,
} from "three/tsl";
import { ao } from "three/examples/jsm/tsl/display/GTAONode.js";
import { traa } from "three/examples/jsm/tsl/display/TRAANode.js";

export interface ComposerHandle {
  render: () => void;
  setSize: (width: number, height: number) => void;
  setAoRadius: (radius: number) => void;
  setGtaoEnabled: (enabled: boolean) => void;
  setAaEnabled: (enabled: boolean) => void;
  dispose: () => void;
}

export function buildComposer(
  renderer: WebGPURenderer,
  scene: THREE.Scene,
  camera: THREE.PerspectiveCamera,
  aoCamera: THREE.PerspectiveCamera,
  gridCamera: THREE.PerspectiveCamera,
): ComposerHandle {
  const postProcessing = new RenderPipeline(renderer);

  const scenePass = pass(scene, camera);
  scenePass.setMRT(mrt({ output, velocity }));
  const colorNode = scenePass.getTextureNode("output");
  const depthNode = scenePass.getTextureNode("depth");
  const velocityNode = scenePass.getTextureNode("velocity");

  // AO input pass: model-only (aoCamera disables FLOOR_LAYER) depth + normal, so
  // the contact-shadow ground + grid never occlude the part's lower walls.
  const aoInputPass = pass(scene, aoCamera);
  aoInputPass.setMRT(mrt({ output, normal: normalView }));
  const aoDepth = aoInputPass.getTextureNode("depth");
  const aoNormal = aoInputPass.getTextureNode("normal");

  const aoPass = ao(aoDepth, aoNormal, camera);
  aoPass.useTemporalFiltering = true; // TRAA below does the cross-frame denoise
  aoPass.samples.value = 32;
  const aoTex = aoPass.getTextureNode();

  // AO toggle without recompiling: 0 → AO forced to 1 (off), 1 → full AO.
  const uAoIntensity = uniform(1);
  const aoFactor = mix(float(1.0), aoTex.r, uAoIntensity);
  const beauty = colorNode.mul(vec4(vec3(aoFactor), 1.0));

  const aaPass = traa(beauty, depthNode, velocityNode, camera);

  // ── work-plane grid overlay (kept OUT of TRAA) ────────────────────────────
  // The grid renders in its own pass (gridCamera sees only GRID_LAYER), so it
  // never enters the TRAA-jittered scene pass. A fine, regular, low-contrast grid
  // is the worst case for temporal AA: sub-pixel jitter + history reprojection
  // average the thin minor lines toward the background until they vanish (the
  // wider, saturated cobalt majors survive). Out of TRAA, the grid keeps its own
  // crisp analytic (derivative) AA.
  //
  // Occlusion: composite the grid over the post-TRAA beauty, masked by a depth
  // test against the MODEL-ONLY depth (aoInputPass). The part sits on the grid,
  // so wherever the model covers a pixel its depth is in front of the grid plane
  // → grid hidden; elsewhere the grid shows. Comparing against model-only depth
  // (no ground) sidesteps the coplanar contact-shadow plane at the same y=0.
  const gridPass = pass(scene, gridCamera);
  const gridColor = gridPass.getTextureNode("output"); // premultiplied over transparent clear
  const gridDepth = gridPass.getTextureNode("depth");
  // 1 where the grid plane is at/in front of the model (i.e. not covered by it).
  const gridMask = step(gridDepth.r, aoDepth.r);
  const gridSrcA = gridColor.a.mul(gridMask);
  const gridSrcRgb = gridColor.rgb.mul(gridMask);

  let aaEnabled = true;
  const applyOutput = () => {
    // aaPass (TRAANode) carries the same vec4 swizzles as `beauty` at runtime;
    // @types/three just doesn't surface them, hence the cast.
    const base = aaEnabled ? (aaPass as unknown as typeof beauty) : beauty;
    // Premultiplied "over": out = src + dst·(1 − srcA).
    const inv = float(1.0).sub(gridSrcA);
    postProcessing.outputNode = vec4(
      gridSrcRgb.add(base.rgb.mul(inv)),
      gridSrcA.add(base.a.mul(inv)),
    );
    postProcessing.needsUpdate = true;
  };
  applyOutput();

  return {
    render: () => postProcessing.render(),
    setSize: () => {
      /* WebGPURenderer.setSize drives the pass; nothing extra needed here. */
    },
    setAoRadius: (radius: number) => {
      aoPass.radius.value = radius;
      aoPass.thickness.value = radius;
    },
    setGtaoEnabled: (enabled: boolean) => {
      uAoIntensity.value = enabled ? 1 : 0;
    },
    setAaEnabled: (enabled: boolean) => {
      aaEnabled = enabled;
      applyOutput();
    },
    dispose: () => {
      // RenderPipeline.dispose() doesn't cascade to the input passes' MRT targets;
      // dispose them so mount/unmount cycles don't leak GPU render targets.
      scenePass.dispose();
      aoInputPass.dispose();
      aoPass.dispose();
      aaPass.dispose();
      gridPass.dispose();
      postProcessing.dispose();
    },
  };
}
