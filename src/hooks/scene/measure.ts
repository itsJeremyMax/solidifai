/**
 * Click-to-measure subsystem for {@link useThreeScene}. The hook owns the scene
 * and the imperative pointer wiring; this module owns the self-contained measure
 * math + in-scene overlay (marker spheres, the A–B line, the DOM distance pill).
 *
 * Kept entirely off React state — the functions mutate the shared `MeasureState`
 * the hook allocates. Types are imported type-only from the hook, so this module
 * has no runtime dependency back on it (no import cycle).
 */
import * as THREE from "three";

import type { MeasureState, SceneRefs } from "../useThreeScene";

/** Cobalt accent (#2B6CFF) used for measure markers, the A–B line, and label. */
export const ACCENT = 0x2b6cff;

/**
 * Handle one measure click: raycast the model, drop a marker at the hit, and on
 * the second point draw the A–B line. A first hit = A, second = B (line +
 * distance), a third click starts a fresh measurement.
 */
export function handleMeasureClick(handle: SceneRefs, e: PointerEvent): void {
  const { measure, camera, modelGroup, renderer } = handle;
  if (modelGroup.children.length === 0) return;

  // A completed pair → next click starts over.
  if (measure.points.length >= 2) clearMeasurement(measure);

  const rect = renderer.domElement.getBoundingClientRect();
  measure.pointer.set(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1,
  );
  measure.raycaster.setFromCamera(measure.pointer, camera);
  const hits = measure.raycaster.intersectObject(modelGroup, true);
  if (hits.length === 0) return;

  const point = hits[0].point.clone();
  measure.points.push(point);

  const marker = new THREE.Mesh(
    measure.markerGeo,
    new THREE.MeshBasicMaterial({ color: ACCENT, depthTest: false }),
  );
  marker.renderOrder = 999; // draw markers on top of the model
  marker.position.copy(point);
  // Scale the marker to a roughly constant on-screen size for this model.
  marker.scale.setScalar(markerRadius(modelGroup));
  measure.group.add(marker);
  measure.markers.push(marker);

  if (measure.points.length === 2) drawMeasureLine(measure);
}

/**
 * A marker radius proportional to the model size (≈0.9% of its max dimension),
 * matching how the AO radius, contact-shadow rig, and work-plane grid all scale
 * to maxDim on load. No absolute floor: a fixed minimum dwarfs sub-unit parts —
 * the prior 0.05 floor gave a ~0.09-unit model a marker larger than the whole
 * object. Because the camera frames the object to fill the view, scaling to the
 * object keeps the marker a roughly constant on-screen size across model sizes.
 */
export function markerRadius(modelGroup: THREE.Group): number {
  const size = new THREE.Box3().setFromObject(modelGroup).getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  return maxDim * 0.009;
}

/** Draw the thin cobalt A–B line once both endpoints exist. */
function drawMeasureLine(measure: MeasureState): void {
  const [a, b] = measure.points;
  const geo = new THREE.BufferGeometry().setFromPoints([a, b]);
  const line = new THREE.Line(
    geo,
    new THREE.LineBasicMaterial({ color: ACCENT, depthTest: false }),
  );
  line.renderOrder = 998;
  measure.group.add(line);
  measure.line = line;
}

/**
 * Re-project the A–B midpoint to screen and position the label there, every RAF
 * frame. Hidden unless a complete pair exists; also hidden when the midpoint is
 * behind the camera. No React state is touched here.
 */
const _mid = new THREE.Vector3();
export function updateMeasureLabel(handle: SceneRefs): void {
  const { measure, camera, renderer } = handle;
  const label = measure.label;
  if (measure.points.length < 2) {
    if (label.style.display !== "none") label.style.display = "none";
    return;
  }

  _mid.addVectors(measure.points[0], measure.points[1]).multiplyScalar(0.5);
  const dist = measure.points[0].distanceTo(measure.points[1]);

  _mid.project(camera);
  // z > 1 means the point is behind the near plane / off-frustum in depth.
  if (_mid.z > 1) {
    if (label.style.display !== "none") label.style.display = "none";
    return;
  }

  const w = renderer.domElement.clientWidth;
  const h = renderer.domElement.clientHeight;
  const x = (_mid.x * 0.5 + 0.5) * w;
  const y = (-_mid.y * 0.5 + 0.5) * h;

  label.textContent = `${dist.toFixed(1)} mm`;
  if (label.style.display !== "block") label.style.display = "block";
  // Round to whole pixels to avoid sub-pixel text shimmer while orbiting.
  label.style.transform = `translate(-50%,-140%) translate(${Math.round(x)}px,${Math.round(y)}px)`;
}

/** Tear down the current measurement: markers, line, label, and point list. */
export function clearMeasurement(measure: MeasureState): void {
  for (const marker of measure.markers) {
    measure.group.remove(marker);
    (marker.material as THREE.Material).dispose();
    // Geometry is shared (measure.markerGeo); freed once on full teardown.
  }
  measure.markers.length = 0;

  if (measure.line) {
    measure.group.remove(measure.line);
    measure.line.geometry.dispose();
    (measure.line.material as THREE.Material).dispose();
    measure.line = null;
  }

  measure.points.length = 0;
  measure.label.style.display = "none";
}
