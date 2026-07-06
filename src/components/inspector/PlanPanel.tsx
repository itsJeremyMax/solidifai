/**
 * PlanPanel — the Inspector's Plan tab. A read-only render of the build brief
 * Sol commits to before building (parts and why, key dims, interfaces,
 * make-it-real), kept live by the `build_brief.json` file-watch.
 *
 * This panel never mutates anything: steering happens in the terminal (Sol runs
 * in a PTY), never here. When there is no brief, it shows a quiet empty state.
 */
import { ArrowLeftRight, ClipboardList } from "lucide-react";

import { useBuildBrief, type BuildBrief } from "../../hooks/useBuildBrief";

/* ── tier chip ───────────────────────────────────────────────────────────── */

// Tier signals rework cost, mapped onto the app palette: skip is a quiet
// neutral, stream rides the accent (normal flow), pause is amber (the beat
// before a fan-out, the same caution color the workspace switcher uses).
const TIER_META: Record<BuildBrief["tier"], { label: string; chip: string; dot: string }> = {
  skip: {
    label: "Skip",
    chip: "bg-surface-2 text-ink-2 border border-line-2",
    dot: "bg-ink-3",
  },
  stream: {
    label: "Stream",
    chip: "bg-accent-tint text-accent",
    dot: "bg-accent",
  },
  pause: {
    label: "Pause",
    chip: "bg-amber/12 text-amber",
    dot: "bg-amber",
  },
};

function TierChip({ tier }: { tier: BuildBrief["tier"] }) {
  const meta = TIER_META[tier] ?? TIER_META.stream;
  return (
    <span
      className={`inline-flex items-center gap-1.25 rounded-md px-1.75 py-0.5 font-mono text-micro font-semibold uppercase tracking-eyebrow ${meta.chip}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}

/* ── section scaffold ────────────────────────────────────────────────────── */

/** An uppercase eyebrow header above a block of brief content. */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-line px-3.5 py-3 last:border-b-0">
      <h3 className="mb-2 font-mono text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
        {title}
      </h3>
      {children}
    </section>
  );
}

/* ── value formatting ────────────────────────────────────────────────────── */

/** A dim value, or a quiet placeholder when Sol left it open. */
function dimValue(value: number | null, unit: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "TBD";
  return `${value} ${unit}`.trim();
}

/** A clearance reads as a millimetre gap, or null (omitted) when unspecified. */
function clearanceLabel(clearance: number | null): string | null {
  if (clearance === null || clearance === undefined || Number.isNaN(clearance)) return null;
  return `${clearance} mm`;
}

/* ── panel ───────────────────────────────────────────────────────────────── */

export default function PlanPanel({ wsPath }: { wsPath: string }) {
  const brief = useBuildBrief(wsPath);

  // The engine validates before it writes, but the panel reads the raw file, so
  // stay tolerant of a hand-edited or partial brief: missing lists render empty,
  // never crash. A summary is what makes a brief worth showing.
  if (!brief || !brief.summary) {
    return (
      <div className="flex flex-col items-center gap-2.5 px-6 pb-8 pt-12 text-center">
        <span className="grid h-9 w-9 place-items-center rounded-xl border border-line-2 bg-surface-2 text-ink-3">
          <ClipboardList size={16} strokeWidth={1.7} />
        </span>
        <p className="text-body text-ink-2">No build brief yet</p>
        <p className="max-w-[15rem] text-caption text-ink-3">
          When Sol plans a part or assembly, the brief shows up here: the parts and why, the
          dimensions that matter, and how the pieces meet.
        </p>
      </div>
    );
  }

  const parts = Array.isArray(brief.parts) ? brief.parts : [];
  const keyDims = Array.isArray(brief.key_dims) ? brief.key_dims : [];
  const interfaces = Array.isArray(brief.interfaces) ? brief.interfaces : [];

  return (
    <div className="pb-2">
      {/* summary + tier header */}
      <div className="border-b border-line px-3.5 py-3">
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <span className="font-mono text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
            Build brief
          </span>
          <TierChip tier={brief.tier} />
        </div>
        <p className="text-body leading-snug text-ink">{brief.summary}</p>
      </div>

      {/* parts — name + why */}
      <Section title={`Parts · ${parts.length}`}>
        <ul className="flex flex-col gap-2">
          {parts.map((p, i) => (
            <li key={`${p.name}-${i}`} className="flex items-start gap-2.5">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-3" />
              <span className="min-w-0">
                <span className="block text-body text-ink">{p.name}</span>
                {(p.why || p.role) && (
                  <span className="mt-0.25 block text-caption text-ink-3">{p.why || p.role}</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      {/* key dims — name / value+unit, with the param it drives */}
      {keyDims.length > 0 && (
        <Section title="Key dimensions">
          <div className="flex flex-col">
            {keyDims.map((d, i) => (
              <div
                key={`${d.name}-${i}`}
                className="flex items-baseline justify-between gap-3 py-1 first:pt-0 last:pb-0"
              >
                <span className="min-w-0">
                  <span className="text-body text-ink">{d.name}</span>
                  {d.drives && (
                    <span className="ml-1.5 font-mono text-micro text-ink-3">→ {d.drives}</span>
                  )}
                </span>
                <span className="shrink-0 font-mono text-caption tabular-nums text-ink-2">
                  {dimValue(d.value, d.unit)}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* interfaces — between, kind, clearance */}
      {interfaces.length > 0 && (
        <Section title="Interfaces">
          <ul className="flex flex-col gap-2">
            {interfaces.map((it, i) => {
              const clearance = clearanceLabel(it.clearance);
              const between = Array.isArray(it.between) ? it.between : [];
              return (
                <li key={`${between.join("-")}-${i}`} className="flex items-start gap-2.5">
                  <ArrowLeftRight
                    size={13}
                    strokeWidth={1.8}
                    className="mt-0.75 shrink-0 text-ink-3"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 text-body text-ink">
                      <span className="min-w-0 truncate">
                        {between[0]}
                        {between[1] && <span className="px-1 text-ink-3">·</span>}
                        {between[1]}
                      </span>
                      <span className="shrink-0 rounded bg-surface-2 px-1.25 py-0.25 font-mono text-micro lowercase text-ink-2">
                        {it.kind}
                      </span>
                    </span>
                    {clearance && (
                      <span className="mt-0.25 block font-mono text-caption text-ink-3">
                        {clearance} clearance
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      {/* make it real — process + material */}
      {brief.make_real && (
        <Section title="Make it real">
          <p className="text-caption leading-relaxed text-ink-2">{brief.make_real}</p>
        </Section>
      )}
    </div>
  );
}
