import { ArrowLeft } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { DOC_REGISTRY } from "../../lib/docs";
import { useGoBack } from "../../hooks/useGoBack";
import { useHeaderSlot } from "../../state/headerSlot";
import { DocsSearchProvider, DocsSearchField } from "./DocsSearch";

const ICON_STROKE = 1.7;

/**
 * DocsLayout - the docs sidebar plus a routed outlet, mirroring SettingsLayout.
 * The grouped nav is built from the docs registry, so adding a markdown file to
 * docs/guide updates the nav with no code change. The centered search field is
 * published into the header; Cmd/Ctrl+K opens the same palette. The provider is
 * mounted here so the palette listens and renders only while on the docs page.
 */
export default function DocsLayout() {
  const goBack = useGoBack("/");

  useHeaderSlot({
    crumb: (
      <div className="flex items-center gap-3.5">
        <button
          type="button"
          onClick={goBack}
          className="inline-flex h-8 items-center gap-1.75 rounded-lg border border-line-2 bg-surface pl-2 pr-3 text-body font-medium text-ink transition-colors duration-150 hover:border-line-3"
        >
          <ArrowLeft className="opacity-70" size={16} strokeWidth={ICON_STROKE} />
          Back
        </button>
        <div className="flex items-center gap-2 text-body text-ink-3">
          <span className="opacity-50">/</span>
          <span className="font-medium text-ink-2">Docs</span>
        </div>
      </div>
    ),
    center: <DocsSearchField />,
  });

  return (
    <DocsSearchProvider>
      <div className="flex min-h-0 w-full flex-1 bg-surface">
        <aside className="flex w-65 shrink-0 flex-col gap-4 overflow-y-auto border-r border-line bg-surface-2 p-3">
          {DOC_REGISTRY.groups.map((group) => (
            <div key={group.label} className="flex flex-col gap-1">
              <div className="px-3 pb-0.5 text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
                {group.label}
              </div>
              {group.pages.map((page) => (
                <NavLink
                  key={page.slug}
                  to={page.slug}
                  replace
                  className={({ isActive }) =>
                    `rounded-xl border px-3 py-2.5 text-left text-body font-medium transition-colors duration-150 ${
                      isActive
                        ? "border-accent-line bg-accent-tint text-ink"
                        : "border-transparent text-ink-2 hover:bg-surface"
                    }`
                  }
                >
                  {page.title}
                </NavLink>
              ))}
            </div>
          ))}
        </aside>
        <section className="flex min-w-0 flex-1 flex-col overflow-hidden bg-surface">
          <Outlet />
        </section>
      </div>
    </DocsSearchProvider>
  );
}
