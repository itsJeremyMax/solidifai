/**
 * WhatsNewModal — the post-update "What's new" surface. On the first launch after
 * an update it takes over the window to walk the user through every CHANGELOG
 * section added since they last opened the app, then records the version as seen.
 *
 * Gating + data come from {@link useWhatsNew}; this file is presentation only. It
 * renders nothing until that hook says `open`. A marquee moment, kept inside the
 * graphite Apple-meets-Atlassian language: a sheen hero, accent-led release notes,
 * one calm "Continue" to dismiss. No copy here uses em dashes.
 */
import { createPortal } from "react-dom";
import { ArrowRight, Bug, Gauge, Sparkles, Wrench, Zap } from "lucide-react";

import { useWhatsNew } from "../hooks/useWhatsNew";

/** Lucide stroke weight matching the rest of the app. */
const ICON_STROKE = 1.7;

/**
 * A glyph per release-please group heading. Falls back to a generic spark so any
 * future group name (Reverts, Documentation, …) still reads as intentional.
 */
function groupGlyph(name: string): React.ReactNode {
  const key = name.toLowerCase();
  if (key.includes("feature")) return <Sparkles size={14} strokeWidth={ICON_STROKE} />;
  if (key.includes("fix") || key.includes("bug"))
    return <Wrench size={14} strokeWidth={ICON_STROKE} />;
  if (key.includes("perf")) return <Gauge size={14} strokeWidth={ICON_STROKE} />;
  if (key.includes("revert")) return <Bug size={14} strokeWidth={ICON_STROKE} />;
  return <Zap size={14} strokeWidth={ICON_STROKE} />;
}

export default function WhatsNewModal() {
  const { open, current, sections, dismiss } = useWhatsNew();

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-100 grid place-items-center bg-scrim p-6 backdrop-blur-md backdrop-saturate-150">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="whatsnew-title"
        className="animate-rise flex max-h-full w-180 max-w-full flex-col overflow-hidden rounded-panel border border-line-2 bg-surface shadow-float"
      >
        {/* Hero */}
        <div className="flex shrink-0 items-center gap-4 border-b border-line bg-sheen px-7 pb-6 pt-7">
          <img
            src="/logo.png"
            alt=""
            draggable={false}
            className="h-12 w-12 shrink-0 select-none rounded-xl border border-line-2 shadow-card"
          />
          <div className="min-w-0">
            <div className="text-micro font-semibold uppercase tracking-eyebrow text-accent">
              Updated to {current}
            </div>
            <h1 id="whatsnew-title" className="mt-1 text-xl font-bold tracking-snug text-ink">
              What's new in solidifai
            </h1>
            <p className="mt-1 text-body leading-normal text-ink-2">
              Everything that landed since you last opened the app.
            </p>
          </div>
        </div>

        {/* Release notes */}
        <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
          <div className="flex flex-col gap-7">
            {sections.map((section) => (
              <section key={section.version}>
                <div className="flex items-baseline gap-2.5">
                  <h2 className="text-base font-bold tracking-snug text-ink">
                    Version {section.version}
                  </h2>
                  {section.date && (
                    <span className="font-mono text-caption text-ink-3">{section.date}</span>
                  )}
                </div>

                <div className="mt-3 flex flex-col gap-4">
                  {Object.entries(section.groups)
                    .filter(([, entries]) => entries.length > 0)
                    .map(([group, entries]) => (
                      <div key={group}>
                        <div className="mb-2 flex items-center gap-1.75 text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
                          <span className="text-accent">{groupGlyph(group)}</span>
                          {group}
                        </div>
                        <ul className="divide-y divide-line overflow-hidden rounded-panel border border-line bg-surface">
                          {entries.map((entry, i) => (
                            <li
                              key={`${group}-${i}`}
                              className="flex items-start gap-3 px-4 py-2.75"
                            >
                              <span className="mt-1.75 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                              <span className="text-body leading-normal text-ink">{entry}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                </div>
              </section>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="flex shrink-0 items-center justify-end gap-3 border-t border-line bg-surface-2 px-7 py-4">
          <button
            type="button"
            onClick={dismiss}
            autoFocus
            className="inline-flex h-9 items-center gap-1.75 rounded-lg border border-transparent bg-accent px-4.5 text-body font-medium text-white shadow-[0_1px_1px_rgba(27,73,201,.4),inset_0_1px_0_rgba(255,255,255,.25)] transition-colors duration-150 hover:bg-accent-press focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-tint"
          >
            Continue
            <ArrowRight size={15} strokeWidth={2} />
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
