/**
 * MeasurePanel — the Inspector's Measure tab. Three sections:
 *   • Mass & geometry — assembly total (mass / volume / surface area / bbox /
 *     center of mass) plus per-part rows; selecting a part highlights it in the
 *     viewport and expands its detail (bbox, CoM, principal moments of inertia).
 *   • Stress — first-order hot-spots (sharp internal corners), severity-dotted,
 *     each row selects its part. Honest about being a geometric heuristic.
 *   • Fit check — a quick ISO-286 hole/shaft fit calculator (the agent can run
 *     arbitrary tolerance chains; this covers the common mating-pair case).
 *
 * Mass + stress are computed lazily and cached per build (useMeasure/useStress),
 * so opening the tab is the only trigger.
 */
import { useEffect, useMemo, useState } from "react";
import { ChevronDown, RotateCw } from "lucide-react";

import CollapsibleSection from "./CollapsibleSection";
import Select from "../ui/Select";
import { useMeasure } from "../../hooks/useMeasure";
import { useStress } from "../../hooks/useStress";
import { engineToleranceStack } from "../../lib/ipc/engine";
import {
  STRESS_SEVERITIES,
  isSolidPart,
  parseToleranceResult,
  type FitType,
  type MeasurePart,
  type StressHotspot,
  type StressSeverity,
  type ToleranceResult,
} from "../../lib/validation";

/* ─────────────────────────── number formatting ─────────────────────────── */

const fmt = (n: number, d = 1) =>
  n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const triple = (v: number[], d = 1) => v.map((n) => fmt(n, d)).join(", ");

/* A key/value readout row (mirrors the Model tab's InfoRow). */
function Row({ k, v, mono = true }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3 px-3.5 py-1.5 text-xs">
      <span className="shrink-0 text-ink-3">{k}</span>
      <span
        className={`min-w-0 truncate text-right ${mono ? "font-mono tabular-nums" : ""} text-ink`}
      >
        {v}
      </span>
    </div>
  );
}

/* ──────────────────────────── mass & geometry ──────────────────────────── */

function PartDetail({ p }: { p: MeasurePart }) {
  if (!isSolidPart(p)) return null;
  return (
    <div className="bg-surface-2/60 pb-1.5">
      <Row k="Volume" v={`${fmt(p.volume / 1000, 2)} cm³`} />
      <Row k="Surface area" v={`${fmt(p.surfaceArea / 100, 1)} cm²`} />
      <Row k="Bounding box" v={`${triple(p.bbox.size)} mm`} />
      <Row k="Center of mass" v={`${triple(p.centerOfMass)} mm`} />
      <Row k="Inertia I₁·I₂·I₃" v={`${triple(p.inertia.principalMoments, 0)} g·mm²`} />
    </div>
  );
}

function PartRow({
  p,
  selected,
  onSelect,
}: {
  p: MeasurePart;
  selected: boolean;
  onSelect: () => void;
}) {
  const solid = isSolidPart(p);
  return (
    <>
      <button
        type="button"
        onClick={onSelect}
        className={
          selected
            ? "flex w-full items-center gap-2 bg-accent-tint px-3.5 py-1.75 text-left shadow-[inset_2px_0_0_var(--color-accent)]"
            : "flex w-full items-center gap-2 px-3.5 py-1.75 text-left transition-colors hover:bg-surface-2"
        }
      >
        <ChevronDown
          size={12}
          strokeWidth={2.4}
          className={`shrink-0 text-ink-3 transition-transform duration-200 ${
            selected ? "" : "-rotate-90"
          }`}
        />
        <span className="min-w-0 flex-1 truncate text-body text-ink">{p.partName}</span>
        <span className="shrink-0 font-mono text-caption tabular-nums text-ink-2">
          {solid ? `${fmt(p.mass!, 2)} g` : "ref"}
        </span>
      </button>
      {selected && <PartDetail p={p} />}
    </>
  );
}

function MassSection({
  buildId,
  active,
  selectedId,
  onSelectPart,
}: {
  buildId: number;
  active: boolean;
  selectedId: string | null;
  onSelectPart: (id: string | null) => void;
}) {
  const { report, loading, error, refresh } = useMeasure(buildId, active);

  if (loading && !report)
    return <p className="px-3.5 py-2.5 text-caption text-ink-3">Measuring…</p>;
  if (error && !report)
    return (
      <button
        type="button"
        onClick={refresh}
        className="mx-3.5 my-2.5 inline-flex items-center gap-1.5 rounded-md border border-line-2 bg-surface px-2.5 py-1 text-caption text-ink-2 transition-colors hover:text-ink"
      >
        <RotateCw size={12} strokeWidth={2} />
        {error} Try again
      </button>
    );
  if (!report) return null;

  const { total } = report;
  const solids = report.parts.filter(isSolidPart);
  const material = solids.length === 1 ? solids[0].material : "mixed";

  return (
    <div className="pb-1.5">
      {/* hero: total mass */}
      <div className="flex items-baseline gap-2 px-3.5 pt-2.5 pb-1.5">
        <span className="font-mono text-2xl font-semibold tracking-tight tabular-nums text-ink">
          {fmt(total.mass, total.mass < 10 ? 2 : 1)}
        </span>
        <span className="text-body text-ink-3">g</span>
        <span className="ml-auto truncate text-caption text-ink-3">
          {material}
          {solids.length > 1 ? ` · ${solids.length} parts` : ""}
        </span>
      </div>

      {/* assembly readout */}
      <Row k="Volume" v={`${fmt(total.volume / 1000, 2)} cm³`} />
      <Row k="Center of mass" v={`${triple(total.centerOfMass)} mm`} />

      {/* per-part rows (only when there's more than one part) */}
      {solids.length > 1 && (
        <div className="mt-1.5 border-t border-line pt-0.5">
          {report.parts.map((p) => (
            <PartRow
              key={p.partId}
              p={p}
              selected={selectedId === p.partId}
              onSelect={() => onSelectPart(selectedId === p.partId ? null : p.partId)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ───────────────────────────── stress hot-spots ────────────────────────── */

const STRESS_DOT: Record<StressSeverity, string> = {
  warning: "bg-amber",
  advisory: "bg-ink-3",
};

function HotspotRow({
  h,
  selected,
  onClick,
}: {
  h: StressHotspot;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        selected
          ? "flex w-full items-start gap-2.5 bg-accent-tint px-3.5 py-2 text-left shadow-[inset_2px_0_0_var(--color-accent)]"
          : "flex w-full items-start gap-2.5 px-3.5 py-2 text-left transition-colors hover:bg-surface-2"
      }
    >
      <span className={`mt-1.25 h-2 w-2 shrink-0 rounded-full ${STRESS_DOT[h.severity]}`} />
      <span className="min-w-0 flex-1">
        <span className="block text-body text-ink">{h.message}</span>
        <span className="mt-0.5 block text-caption text-ink-3">{h.hint}</span>
      </span>
    </button>
  );
}

function StressSection({
  buildId,
  active,
  selectedId,
  onSelectPart,
}: {
  buildId: number;
  active: boolean;
  selectedId: string | null;
  onSelectPart: (id: string | null) => void;
}) {
  const { report, loading, error, refresh } = useStress(buildId, active);

  const counts = report?.summary ?? { warning: 0, advisory: 0, parts: 0 };
  const total = counts.warning + counts.advisory;

  return (
    <div className="pb-1.5">
      <p className="px-3.5 pb-1.5 pt-2 text-caption text-ink-3">
        Where load concentrates, not a solved stress field.
      </p>
      <div className="flex items-center justify-between gap-2 px-3.5 pb-1.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {total > 0 ? (
            STRESS_SEVERITIES.map((s) =>
              counts[s] > 0 ? (
                <span key={s} className="inline-flex items-center gap-1.5 text-caption text-ink-2">
                  <span className={`h-2 w-2 rounded-full ${STRESS_DOT[s]}`} />
                  {counts[s]} {s}
                </span>
              ) : null,
            )
          ) : report ? (
            <span className="inline-flex items-center gap-1.5 text-caption text-engine">
              <span className="h-2 w-2 rounded-full bg-engine" />
              No stress risks found
            </span>
          ) : loading ? (
            <span className="text-caption text-ink-3">Checking…</span>
          ) : (
            <span className="text-caption text-ink-3">—</span>
          )}
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={loading}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-caption text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink disabled:hover:bg-transparent"
        >
          <RotateCw size={11} strokeWidth={2} className={loading ? "animate-spin" : ""} />
          {loading ? "Checking" : "Re-run"}
        </button>
      </div>
      {error && !report && <p className="px-3.5 py-1.5 text-caption text-ink-3">{error}</p>}
      {report?.parts.map((part) =>
        part.hotspots.length === 0 ? null : (
          <div key={part.partId}>
            {report.parts.filter((p) => p.hotspots.length > 0).length > 1 && (
              <div className="px-3.5 pb-1 pt-2 text-micro font-bold uppercase tracking-eyebrow text-ink-3">
                {part.partName}
              </div>
            )}
            {part.hotspots.map((h, i) => {
              const selected = selectedId === part.partId;
              return (
                <HotspotRow
                  key={`${part.partId}-${i}`}
                  h={h}
                  selected={selected}
                  onClick={() => onSelectPart(selected ? null : part.partId)}
                />
              );
            })}
          </div>
        ),
      )}
    </div>
  );
}

/* ──────────────────────────────── fit check ────────────────────────────── */

const HOLE_FITS = ["H7", "H8", "H9", "H11"];
const SHAFT_FITS = ["g6", "h6", "h7", "f7", "k6", "p6"];

const FIT_TONE: Record<FitType, string> = {
  clearance: "text-engine",
  transition: "text-amber",
  interference: "text-danger",
};

function FitSelect({
  value,
  options,
  onChange,
  label,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
  label: string;
}) {
  return (
    <div className="flex flex-1 flex-col gap-1">
      <span className="text-micro font-bold uppercase tracking-eyebrow text-ink-3">{label}</span>
      <Select
        value={value}
        onChange={onChange}
        ariaLabel={label}
        options={options.map((o) => ({ value: o, label: o }))}
      />
    </div>
  );
}

function FitCheckSection() {
  const [nominal, setNominal] = useState(10);
  const [hole, setHole] = useState("H7");
  const [shaft, setShaft] = useState("g6");
  const [result, setResult] = useState<ToleranceResult | null>(null);

  const chain = useMemo(
    () => [
      { label: "hole", nominal, fit: hole, direction: 1 },
      { label: "shaft", nominal, fit: shaft, direction: -1 },
    ],
    [nominal, hole, shaft],
  );

  useEffect(() => {
    let live = true;
    if (!Number.isFinite(nominal) || nominal <= 0) {
      setResult(null);
      return;
    }
    void engineToleranceStack(chain).then((raw) => {
      if (live) setResult(raw ? parseToleranceResult(raw) : null);
    });
    return () => {
      live = false;
    };
  }, [chain, nominal]);

  const fit = result?.fit;

  return (
    <div className="px-3.5 pb-3 pt-2">
      <div className="flex items-end gap-2">
        <label className="flex w-16 flex-col gap-1">
          <span className="text-micro font-bold uppercase tracking-eyebrow text-ink-3">Ø mm</span>
          <input
            type="number"
            min={0.1}
            step={0.5}
            value={nominal}
            onChange={(e) => setNominal(parseFloat(e.target.value))}
            className="h-8.5 w-full rounded-lg border border-line-2 bg-surface px-2.75 font-mono text-caption text-ink transition-colors duration-150 hover:border-line-3 focus:border-accent-line focus:outline-none"
          />
        </label>
        <FitSelect label="Hole" value={hole} options={HOLE_FITS} onChange={setHole} />
        <FitSelect label="Shaft" value={shaft} options={SHAFT_FITS} onChange={setShaft} />
      </div>
      {fit ? (
        <div className="mt-2.5 flex items-center justify-between rounded-md bg-surface-2 px-2.5 py-1.5">
          <span className={`text-caption font-semibold capitalize ${FIT_TONE[fit.type]}`}>
            {fit.type}
          </span>
          <span className="font-mono text-caption tabular-nums text-ink-2">
            gap {fmt(fit.minGap, 3)} … {fmt(fit.maxGap, 3)} mm
          </span>
        </div>
      ) : (
        <p className="mt-2.5 text-caption text-ink-3">
          Pick a hole and shaft fit to check clearance.
        </p>
      )}
    </div>
  );
}

/* ──────────────────────────────── panel ────────────────────────────────── */

export default function MeasurePanel({
  buildId,
  active,
  selectedId,
  onSelectPart,
}: {
  buildId: number;
  active: boolean;
  selectedId: string | null;
  onSelectPart: (id: string | null) => void;
}) {
  const [open, setOpen] = useState({ mass: true, stress: true, fit: false });
  const toggle = (k: keyof typeof open) => setOpen((o) => ({ ...o, [k]: !o[k] }));

  if (buildId < 0) {
    return (
      <p className="px-3.5 py-3.5 text-body text-ink-3">
        Build a model to measure its mass, balance, and stress.
      </p>
    );
  }

  return (
    <div className="pb-2">
      <CollapsibleSection title="Mass & geometry" open={open.mass} onToggle={() => toggle("mass")}>
        <MassSection
          buildId={buildId}
          active={active && open.mass}
          selectedId={selectedId}
          onSelectPart={onSelectPart}
        />
      </CollapsibleSection>

      <CollapsibleSection title="Stress" open={open.stress} onToggle={() => toggle("stress")}>
        <StressSection
          buildId={buildId}
          active={active && open.stress}
          selectedId={selectedId}
          onSelectPart={onSelectPart}
        />
      </CollapsibleSection>

      <CollapsibleSection title="Fit check" open={open.fit} onToggle={() => toggle("fit")}>
        <FitCheckSection />
      </CollapsibleSection>
    </div>
  );
}
