/**
 * ActivityPanel — the Inspector's Activity tab: the build brief Sol commits to
 * before building (read-only; steering happens in the terminal) above the
 * edit-history list (click a row to restore).
 */
import { useEffect, useRef, useState } from "react";
import { ArrowLeftRight, ClipboardList } from "lucide-react";

import CollapsibleSection from "./CollapsibleSection";
import History from "../History";
import type { BuildBrief } from "../../hooks/useBuildBrief";
import type { SectionKey, SectionState } from "../../state/useInspectorPrefs";

/** Text clamped to a few lines with a Show more toggle when it overflows. */
function ClampedText({ text, className }: { text: string; className: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);

  // Re-measure when the text changes (a new brief) — clamped scrollHeight >
  // clientHeight means there is hidden content worth a toggle.
  useEffect(() => {
    setExpanded(false);
    const el = ref.current;
    if (el) setOverflows(el.scrollHeight > el.clientHeight + 1);
  }, [text]);

  return (
    <>
      <p ref={ref} className={`${className} ${expanded ? "" : "line-clamp-3"}`}>
        {text}
      </p>
      {(overflows || expanded) && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="mt-0.5 text-caption font-medium text-accent transition-opacity hover:opacity-80"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </>
  );
}

/* ── tier chip ───────────────────────────────────────────────────────────── */

// Tier signals rework cost: skip is a quiet neutral, stream rides the accent
// (normal flow), pause is amber (the beat before a fan-out).
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

/** An uppercase eyebrow header above a block of brief content. */
function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="px-3.5 py-2.5">
      <h3 className="mb-2 font-mono text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
        {title}
      </h3>
      {children}
    </section>
  );
}

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

/* ── brief section body ──────────────────────────────────────────────────── */

function BriefSection({ brief }: { brief: BuildBrief | null }) {
  // The engine validates before it writes, but this reads the raw file, so
  // stay tolerant of a hand-edited or partial brief: missing lists render
  // empty, never crash. A summary is what makes a brief worth showing.
  if (!brief || !brief.summary) {
    return (
      <div className="flex flex-col items-center gap-2 px-6 pb-5 pt-3 text-center">
        <span className="grid h-8 w-8 place-items-center rounded-lg border border-line-2 bg-surface-2 text-ink-3">
          <ClipboardList size={14} strokeWidth={1.7} />
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
    <div className="pb-1">
      {/* summary + tier */}
      <div className="px-3.5 pb-2.5 pt-0.5">
        <ClampedText text={brief.summary} className="text-body leading-snug text-ink" />
        <div className="mt-1.5">
          <TierChip tier={brief.tier} />
        </div>
      </div>

      {/* parts — name + why */}
      <Block title={`Parts · ${parts.length}`}>
        <ul className="flex flex-col gap-2">
          {parts.map((p, i) => (
            <li key={p.id || `${p.name}-${i}`} className="flex items-start gap-2.5">
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
      </Block>

      {/* key dims — name / value+unit, with the param it drives */}
      {keyDims.length > 0 && (
        <Block title="Key dimensions">
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
        </Block>
      )}

      {/* interfaces — between, kind, clearance */}
      {interfaces.length > 0 && (
        <Block title="Interfaces">
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
        </Block>
      )}

      {/* make it real — process + material */}
      {brief.make_real && (
        <Block title="Make it real">
          <ClampedText text={brief.make_real} className="text-caption leading-relaxed text-ink-2" />
        </Block>
      )}
    </div>
  );
}

/* ── panel ───────────────────────────────────────────────────────────────── */

export default function ActivityPanel({
  brief,
  open,
  onToggleSection,
}: {
  brief: BuildBrief | null;
  open: SectionState;
  onToggleSection: (k: SectionKey) => void;
}) {
  return (
    <div className="pb-2">
      <CollapsibleSection
        title="Build brief"
        open={open["activity.brief"]}
        onToggle={() => onToggleSection("activity.brief")}
      >
        <BriefSection brief={brief} />
      </CollapsibleSection>

      <CollapsibleSection
        title="History"
        open={open["activity.history"]}
        onToggle={() => onToggleSection("activity.history")}
      >
        <History />
      </CollapsibleSection>
    </div>
  );
}
