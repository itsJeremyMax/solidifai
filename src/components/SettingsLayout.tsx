import { ArrowLeft, ArrowUpRight } from "lucide-react";
import { Link, NavLink, Outlet } from "react-router-dom";

import type { SettingsSection } from "./settings/sections";
import { useGoBack } from "../hooks/useGoBack";
import { useHeaderSlot } from "../state/headerSlot";

const ICON_STROKE = 1.7;

/** Group a section list by `group`, preserving first-seen order. */
function groupedSections(
  sections: SettingsSection[],
): { label: string; items: SettingsSection[] }[] {
  const order: string[] = [];
  const byGroup = new Map<string, SettingsSection[]>();
  for (const s of sections) {
    if (!byGroup.has(s.group)) {
      byGroup.set(s.group, []);
      order.push(s.group);
    }
    byGroup.get(s.group)!.push(s);
  }
  return order.map((label) => ({ label, items: byGroup.get(label)! }));
}

export interface SettingsLayoutProps {
  /** The section registry to render (app vs workspace). */
  sections: SettingsSection[];
  /** Crumb label ("Settings" or "Workspace settings"). */
  title: string;
  /** Optional link to the sibling settings page (e.g. App settings from a workspace). */
  crossLink?: { to: string; label: string };
}

/**
 * SettingsLayout — the settings sidebar + a routed `<Outlet/>` for the active
 * section. The section list is passed in so the same layout drives both App
 * settings (`/settings`) and Workspace settings (`/w/:wsPath/settings`); the
 * grouped nav and the routes both derive from that list, so they can never drift.
 * Group headers show only when there is more than one group; a single-group page
 * (workspace settings) reads as a flat list.
 */
export default function SettingsLayout({ sections, title, crossLink }: SettingsLayoutProps) {
  const goBack = useGoBack("/");
  const groups = groupedSections(sections);
  const showGroupHeaders = groups.length > 1;

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
          <span className="font-medium text-ink-2">{title}</span>
        </div>
      </div>
    ),
  });

  return (
    <div className="flex min-h-0 w-full flex-1 bg-surface">
      {/* Left section nav — labelled groups, driven by the passed registry. */}
      <aside className="flex w-65 shrink-0 flex-col gap-4 overflow-y-auto border-r border-line bg-surface-2 p-3">
        {groups.map((group) => (
          <div key={group.label} className="flex flex-col gap-1">
            {showGroupHeaders && (
              <div className="px-3 pb-0.5 text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
                {group.label}
              </div>
            )}
            {group.items.map((s) => (
              <NavLink
                key={s.id}
                to={s.id}
                replace
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left transition-colors duration-150 ${
                    isActive
                      ? "border-accent-line bg-accent-tint"
                      : "border-transparent hover:bg-surface"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span className={isActive ? "text-accent" : "text-ink-3"}>{s.icon}</span>
                    <span
                      className={`text-body font-medium ${isActive ? "text-ink" : "text-ink-2"}`}
                    >
                      {s.label}
                    </span>
                  </>
                )}
              </NavLink>
            ))}
          </div>
        ))}

        {crossLink && (
          <Link
            to={crossLink.to}
            className="mt-auto flex items-center gap-2 rounded-xl border border-line-2 bg-surface px-3 py-2.5 text-body font-medium text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink"
          >
            <ArrowUpRight size={16} strokeWidth={ICON_STROKE} className="text-ink-3" />
            {crossLink.label}
          </Link>
        )}
      </aside>

      {/* Right section content. */}
      <section className="flex min-w-0 flex-1 flex-col overflow-y-auto bg-surface">
        <Outlet />
      </section>
    </div>
  );
}
