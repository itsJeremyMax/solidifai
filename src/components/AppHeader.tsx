import { NavLink } from "react-router-dom";
import { HeaderSlotOutlet } from "../state/headerSlot";
import { WorkspaceSwitcherBar } from "./WorkspaceSwitcher";

/**
 * AppHeader — the one persistent window chrome. The brand sits on the left and
 * never unmounts (it lives in {@link AppLayout}, above the routed outlet), so the
 * logo is pixel-stable across every page. Pages publish their contextual crumb +
 * right-side actions through the header slot; the header itself knows nothing
 * about any page.
 *
 * Chrome classes are the canonical set the editor/settings/materials headers
 * already shared, so the look is unchanged — only the duplication is gone.
 */

/** The app logo glyph. Scales slightly on brand hover. */
export function BrandMark({ size = 24 }: { size?: number }) {
  return (
    <img
      src="/logo.png"
      alt=""
      draggable={false}
      className="shrink-0 select-none rounded-md border border-line-2 transition-transform duration-150 group-hover:scale-105"
      style={{ height: size, width: size }}
    />
  );
}

export default function AppHeader() {
  return (
    <header className="relative z-40 flex h-13.5 shrink-0 grow-0 basis-13.5 items-center gap-3.5 border-b border-line bg-sheen px-4 backdrop-blur-lg backdrop-saturate-150">
      {/* Brand -> home. The single fixed anchor of the chrome. */}
      <NavLink
        to="/"
        title="Home"
        className="group -ml-1.5 flex items-center gap-2.25 rounded-lg px-1.5 py-1 text-base font-bold tracking-snug text-ink transition-colors duration-150 hover:bg-surface-2"
      >
        <BrandMark />
        solidifai
      </NavLink>

      {/* Contextual crumb (back + page title), published by non-editor pages.
          Sits right after the brand so it reads as a breadcrumb, solidifai / Page;
          the editor viewport publishes none. */}
      <HeaderSlotOutlet which="crumb" />

      {/* Workspace switcher. On the editor viewport it's the full segmented tab
          control (the focused pill is the workspace identity, absorbing the crumb);
          on every other surface it folds to a compact chip after the crumb, so the
          per-workspace tabs never pollute a global page. Empty with no open tab. */}
      <WorkspaceSwitcherBar />

      {/* Centered region. Doubles as the flex spacer: empty on most pages (so their
          layout is unchanged), it carries a page's centered chrome (the docs search)
          when published. The published element decides how it sits here. */}
      <div className="flex min-w-0 flex-1 items-center justify-center">
        <HeaderSlotOutlet which="center" />
      </div>

      {/* Right-side actions published by the current page. Pinned (shrink-0) so the
          cluster keeps its intrinsic width and never compresses its pills into a
          wrapped, ragged block; the centered region above absorbs any squeeze instead. */}
      <div className="flex shrink-0 items-center gap-2.5">
        <HeaderSlotOutlet which="actions" />
      </div>
    </header>
  );
}
