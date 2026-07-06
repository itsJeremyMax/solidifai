import { ArrowLeft } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { SETTINGS_SECTIONS, type SettingsSection } from "./settings/sections";
import { useHeaderSlot } from "../state/headerSlot";

const ICON_STROKE = 1.7;

/** Group the registry by `group`, preserving first-seen order. */
function groupedSections(): { label: string; items: SettingsSection[] }[] {
  const order: string[] = [];
  const byGroup = new Map<string, SettingsSection[]>();
  for (const s of SETTINGS_SECTIONS) {
    if (!byGroup.has(s.group)) {
      byGroup.set(s.group, []);
      order.push(s.group);
    }
    byGroup.get(s.group)!.push(s);
  }
  return order.map((label) => ({ label, items: byGroup.get(label)! }));
}

/**
 * SettingsLayout — the settings sidebar + a routed `<Outlet/>` for the active
 * section. Both the grouped nav and the routes derive from the section registry,
 * so the sidebar and routing can never drift. Reused verbatim at `/settings`
 * (global) and `/w/:wsPath/settings` (editor scope); the relative `NavLink`s and
 * a history `Back` keep it scope-agnostic.
 */
export default function SettingsLayout() {
  const navigate = useNavigate();
  const groups = groupedSections();

  useHeaderSlot({
    crumb: (
      <div className="flex items-center gap-3.5">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="inline-flex h-8 items-center gap-1.75 rounded-lg border border-line-2 bg-surface pl-2 pr-3 text-body font-medium text-ink transition-colors duration-150 hover:border-line-3"
        >
          <ArrowLeft className="opacity-70" size={16} strokeWidth={ICON_STROKE} />
          Back
        </button>
        <div className="flex items-center gap-2 text-body text-ink-3">
          <span className="opacity-50">/</span>
          <span className="font-medium text-ink-2">Settings</span>
        </div>
      </div>
    ),
  });

  return (
    <div className="flex min-h-0 w-full flex-1 bg-surface">
      {/* Left section nav — labelled groups, driven by the registry. */}
      <aside className="flex w-65 shrink-0 flex-col gap-4 overflow-y-auto border-r border-line bg-surface-2 p-3">
        {groups.map((group) => (
          <div key={group.label} className="flex flex-col gap-1">
            <div className="px-3 pb-0.5 text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
              {group.label}
            </div>
            {group.items.map((s) => (
              <NavLink
                key={s.id}
                to={s.id}
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
      </aside>

      {/* Right section content. */}
      <section className="flex min-w-0 flex-1 flex-col overflow-y-auto bg-surface">
        <Outlet />
      </section>
    </div>
  );
}
