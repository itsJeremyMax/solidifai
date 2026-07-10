/**
 * MeasureSection — the Model tab's numbers: instant manifest readout (mass,
 * volume, bbox, watertight/valid) + the engine's deeper measure report
 * (center of mass, per-part rows) fetched lazily while the section is open.
 */
import { ChevronDown, RotateCw } from "lucide-react";

import { useMeasure } from "../../hooks/useMeasure";
import { isSolidPart, type MeasurePart } from "../../lib/validation";
import type { ModelInfo } from "../../lib/artifacts";
import { round1 } from "../../lib/format";

const fmt = (n: number, d = 1) =>
  n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const triple = (v: number[], d = 1) => v.map((n) => fmt(n, d)).join(", ");

/** A key/value readout row. `ok` colors the value engine-green; `bad` red. */
function Row({
  k,
  v,
  ok = false,
  bad = false,
}: {
  k: string;
  v: string;
  ok?: boolean;
  bad?: boolean;
}) {
  const tone = bad ? "text-danger" : ok ? "text-engine" : "text-ink";
  return (
    <div className="flex justify-between gap-3 px-3.5 py-1.5 text-xs">
      <span className="shrink-0 text-ink-3">{k}</span>
      <span className={`min-w-0 truncate text-right font-mono tabular-nums ${tone}`}>{v}</span>
    </div>
  );
}

/* ─── per-part rows (report layer) ───────────────────────────────────────── */

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

/* ─── section ────────────────────────────────────────────────────────────── */

export default function MeasureSection({
  model,
  active,
  selectedId,
  onSelectPart,
}: {
  model: ModelInfo | null;
  /** True while the Model tab is shown AND this section is open. */
  active: boolean;
  selectedId: string | null;
  onSelectPart: (id: string | null) => void;
}) {
  const buildId = model?.buildId ?? -1;
  const { report, loading, error, refresh } = useMeasure(buildId, active && buildId >= 0);

  if (model === null) {
    return <div className="px-3.5 pb-3 pt-0.5 text-xs text-ink-3">No model yet</div>;
  }

  const solids = report?.parts.filter(isSolidPart) ?? [];

  return (
    <div className="pb-1.5">
      {/* hero: total mass, straight off the manifest so it never waits */}
      <div className="flex items-baseline gap-2 px-3.5 pb-1.5 pt-1">
        <span className="font-mono text-2xl font-semibold tracking-tight tabular-nums text-ink">
          {fmt(model.mass.value, model.mass.value < 10 ? 2 : 1)}
        </span>
        <span className="text-body text-ink-3">g</span>
        <span className="ml-auto truncate text-caption text-ink-3">{model.mass.material}</span>
      </div>

      {/* manifest readout */}
      <Row k="Volume" v={`${(model.volume / 1000).toFixed(2)} cm³`} />
      <Row
        k="Bounding box"
        v={`${round1(model.bbox.size[0])}×${round1(model.bbox.size[1])}×${round1(
          model.bbox.size[2],
        )} mm`}
      />
      <Row
        k="Watertight"
        v={model.manifold ? "✓ yes" : "✗ no"}
        ok={model.manifold}
        bad={!model.manifold}
      />
      <Row k="Valid" v={model.valid ? "✓ yes" : "✗ no"} ok={model.valid} bad={!model.valid} />

      {/* report layer */}
      {report ? (
        <>
          <Row k="Center of mass" v={`${triple(report.total.centerOfMass)} mm`} />
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
        </>
      ) : loading ? (
        <p className="px-3.5 py-1.5 text-caption text-ink-3">Measuring…</p>
      ) : error ? (
        <button
          type="button"
          onClick={refresh}
          className="mx-3.5 my-1.5 inline-flex items-center gap-1.5 rounded-md border border-line-2 bg-surface px-2.5 py-1 text-caption text-ink-2 transition-colors hover:text-ink"
        >
          <RotateCw size={12} strokeWidth={2} />
          {error} Try again
        </button>
      ) : null}
    </div>
  );
}
