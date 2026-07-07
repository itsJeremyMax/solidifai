/**
 * ReleaseNotesGroups — renders a changelog version's grouped entries (Features,
 * Bug Fixes, …) as accent-led bullet lists, one bordered list per group with a
 * glyphed eyebrow. Shared by the post-update {@link WhatsNewModal} and the
 * Settings → About "What's new" card so the treatment is defined once.
 */
import { Bug, Gauge, Sparkles, Wrench, Zap } from "lucide-react";

import { nonEmptyGroups } from "../lib/changelog";

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

export default function ReleaseNotesGroups({ groups }: { groups: Record<string, string[]> }) {
  return (
    <div className="flex flex-col gap-4">
      {nonEmptyGroups(groups).map(([group, entries]) => (
        <div key={group}>
          <div className="mb-2 flex items-center gap-1.75 text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
            <span className="text-accent">{groupGlyph(group)}</span>
            {group}
          </div>
          <ul className="divide-y divide-line overflow-hidden rounded-panel border border-line bg-surface">
            {entries.map((entry, i) => (
              <li key={`${group}-${i}`} className="flex items-start gap-3 px-4 py-2.75">
                <span className="mt-1.75 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                <span className="text-body leading-normal text-ink">{entry}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
