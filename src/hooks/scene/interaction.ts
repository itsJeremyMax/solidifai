/**
 * DOM event wiring for the {@link useThreeScene} viewport: click-to-measure
 * pointer handlers, Escape-to-clear, right-click pick, and the render-request
 * self-heals (pointer move/enter, window focus, tab visibility return).
 *
 * Every handler here reads/writes state that already lives on `SceneRefs`
 * (`measure`, `pick`, `requestRender`) rather than closing over hook-scope
 * variables, so there is nothing extra to thread through an `opts` param —
 * `handle` alone gives each handler the same live objects the original inline
 * closures captured. `handleMeasureClick`/`clearMeasurement` are imported
 * straight from the measure module, matching how the hook itself calls them.
 */
import { glbWorldToEngineMm } from "../../lib/coords";
import type { SceneRefs } from "./types";
import { clearMeasurement, handleMeasureClick } from "./measure";

/** Max pointer travel (px²) between down/up that still counts as a "click". */
const CLICK_SLOP_SQ = 5 * 5;

/**
 * Install the viewport's pointer/keyboard/context-menu/pick/focus listeners
 * and return a teardown that removes exactly what was added.
 */
export function attachInteraction(handle: SceneRefs): () => void {
  const { renderer, camera, modelGroup, measure, pick, requestRender } = handle;

  // ── measure pointer handlers (click = non-drag pointerdown→up) ──
  const onPointerDown = (e: PointerEvent) => {
    if (!measure.enabled || e.button !== 0) return;
    measure.downX = e.clientX;
    measure.downY = e.clientY;
  };
  const onPointerUp = (e: PointerEvent) => {
    if (!measure.enabled || e.button !== 0) return;
    const dx = e.clientX - measure.downX;
    const dy = e.clientY - measure.downY;
    // A drag (orbit) moves the pointer; only a near-stationary click picks.
    if (dx * dx + dy * dy > CLICK_SLOP_SQ) return;
    handleMeasureClick(handle, e);
    requestRender();
  };
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape" && measure.enabled) {
      clearMeasurement(measure);
      requestRender();
    }
  };
  // Right-click context menu: raycast and fire the pick callback if registered.
  const onContextMenu = (e: MouseEvent) => {
    e.preventDefault();
    if (!pick.onPick) return;
    const screenX = e.clientX;
    const screenY = e.clientY;
    if (modelGroup.children.length === 0) {
      pick.onPick({ pointMm: null, screenX, screenY });
      return;
    }
    const rect = renderer.domElement.getBoundingClientRect();
    measure.pointer.set(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    measure.raycaster.setFromCamera(measure.pointer, camera);
    const hits = measure.raycaster.intersectObject(modelGroup, true);
    pick.onPick({
      pointMm: hits.length ? glbWorldToEngineMm(hits[0].point, modelGroup) : null,
      screenX,
      screenY,
    });
  };
  renderer.domElement.addEventListener("pointerdown", onPointerDown);
  renderer.domElement.addEventListener("pointerup", onPointerUp);
  renderer.domElement.addEventListener("contextmenu", onContextMenu);
  window.addEventListener("keydown", onKeyDown);

  // Self-heal: any pointer over the viewport, or a window refocus / tab return,
  // repaints — so a missed trigger can't leave a stale frame on screen for long.
  // No periodic tick: cursor away + nothing changing ⇒ zero GPU frames.
  const onPointerMove = () => requestRender();
  const onFocus = () => requestRender();
  renderer.domElement.addEventListener("pointermove", onPointerMove);
  renderer.domElement.addEventListener("pointerenter", onPointerMove);
  window.addEventListener("focus", onFocus);
  document.addEventListener("visibilitychange", onFocus);

  return () => {
    renderer.domElement.removeEventListener("pointerdown", onPointerDown);
    renderer.domElement.removeEventListener("pointerup", onPointerUp);
    renderer.domElement.removeEventListener("contextmenu", onContextMenu);
    window.removeEventListener("keydown", onKeyDown);
    renderer.domElement.removeEventListener("pointermove", onPointerMove);
    renderer.domElement.removeEventListener("pointerenter", onPointerMove);
    window.removeEventListener("focus", onFocus);
    document.removeEventListener("visibilitychange", onFocus);
  };
}
