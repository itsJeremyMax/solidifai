/**
 * Small presentation formatters shared across the UI.
 *
 * Pure, dependency-free number/dimension helpers consolidated here so the
 * inspector and the viewport format values identically (no drift between the
 * slider readouts, the dimension info rows, and the viewport HUD).
 *
 * Path (`~`) and relative-time formatters live in `lib/workspaces.ts` next to
 * the workspace types that use them.
 */

/**
 * Round to at most one decimal, dropping a trailing `.0`.
 * e.g. `20 → "20"`, `7.55 → "7.6"`, `7.0 → "7"`.
 */
export function round1(n: number): string {
  const r = Math.round(n * 10) / 10;
  return Number.isInteger(r) ? String(r) : r.toFixed(1);
}

/**
 * Format a `[w, h, d]` size triple as `"20 × 20 × 20"` (each axis via
 * {@link round1}). Used by the viewport HUD; the inspector composes the same
 * `round1` with a `×` separator for its bounding-box row.
 */
export function formatDims(size: [number, number, number]): string {
  return `${round1(size[0])} × ${round1(size[1])} × ${round1(size[2])}`;
}
