/**
 * Shared Tailwind className recipes for the few visual primitives that recur
 * verbatim across components. Each constant captures only the *invariant* set of
 * utilities; per-use deltas (size, padding, position, disabled styling) are
 * appended at the call site.
 *
 * Tailwind emits one atomic rule per utility regardless of class order, so
 * composing `${RECIPE} extra-classes` produces byte-for-byte identical CSS to
 * the original inline strings — these consts are a readability/DRY win with no
 * visual change.
 */

/**
 * The cobalt primary CTA button (the "Export", "Create workspace", "Save",
 * "Rename", "New workspace" buttons). Append per-use sizing/padding such as
 * `h-8 px-3` and any `disabled:*` modifiers.
 */
export const ACCENT_CTA =
  "inline-flex items-center gap-1.75 rounded-lg border border-transparent bg-accent text-body font-medium text-white shadow-[0_1px_1px_rgba(27,73,201,.4),inset_0_1px_0_rgba(255,255,255,.25)] transition-colors duration-150 hover:bg-accent-press";

/**
 * The frosted dropdown/overflow menu panel (workspace switcher, export menu,
 * workspace-card actions). Append per-use positioning + width such as
 * `right-0 top-9.5 w-44`.
 */
export const MENU_PANEL =
  "animate-rise absolute z-30 overflow-hidden rounded-panel border border-line-2 bg-surface p-1.25 shadow-float";
