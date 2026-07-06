/**
 * MakePanel — the Inspector's Make tab. Sections:
 *   • Slicer status — detected name + version, or a quiet install prompt.
 *   • Connections   — the saved connections (read-only here); created + edited on
 *                     the Factory page, and selected below for estimate / open.
 *   • Slice & estimate — on-demand print-time / filament / cost readout, with an
 *                        "approx" note when no slicer is present.
 *   • Auto-orient — suggested print orientation + support-area reduction.
 *                   Display only; "apply" is not wired in the engine.
 *   • Open in OrcaSlicer — hands the current model off to the slicer.
 *
 * All sections degrade gracefully when there is no model (buildId < 0) or no
 * slicer detected.
 */
import { useEffect, useState } from "react";
import { Factory, Printer, RotateCw, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import CollapsibleSection from "./CollapsibleSection";
import Select from "../ui/Select";
import { useFabrication } from "../../hooks/useFabrication";

/* ─── helpers ────────────────────────────────────────────────────────────── */

/** Format seconds → "4h 12m", "12m 30s", "45s". */
function fmtDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/** Reduction percentage, rounded. */
function supportSaving(best: number, worst: number): number {
  if (worst <= 0) return 0;
  return Math.round(((worst - best) / worst) * 100);
}

/* ─── shared row / label primitives ─────────────────────────────────────── */

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 px-3.5 py-1.5 text-xs">
      <span className="shrink-0 text-ink-3">{k}</span>
      <span className="min-w-0 truncate text-right font-mono tabular-nums text-ink">{v}</span>
    </div>
  );
}

/* ─── Slicer status ──────────────────────────────────────────────────────── */

function SlicerSection({ active }: { active: boolean }) {
  const fab = useFabricationCtx();

  // Detect once when the section becomes active, if not yet loaded.
  useEffect(() => {
    if (active && fab.install === null && !fab.loading) {
      void fab.detect();
    }
  }, [active, fab]);

  const { install, loading } = fab;

  return (
    <div className="px-3.5 pb-3 pt-2">
      {loading && install === null ? (
        <p className="text-caption text-ink-3">Detecting…</p>
      ) : install?.found ? (
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-body text-ink">OrcaSlicer</p>
            {install.version && (
              <p className="font-mono text-caption text-ink-3">{install.version}</p>
            )}
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-md bg-engine/10 px-2 py-0.75 text-caption font-medium text-engine">
            <span className="h-1.5 w-1.5 rounded-full bg-engine" />
            Ready
          </span>
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          <p className="text-body text-ink-2">No slicer detected.</p>
          <p className="text-caption text-ink-3">
            Install OrcaSlicer to unlock real print time, exact filament, and direct handoff.
          </p>
          <button
            type="button"
            onClick={() => void fab.detect()}
            disabled={loading}
            className="mt-0.5 inline-flex w-fit items-center gap-1.5 rounded-md border border-line-2 bg-surface px-2.5 py-1 text-caption font-medium text-ink-2 transition-colors hover:border-line-3 hover:text-ink disabled:opacity-50"
          >
            <RotateCw size={11} strokeWidth={2} className={loading ? "animate-spin" : ""} />
            {loading ? "Detecting" : "Detect again"}
          </button>
        </div>
      )}
    </div>
  );
}

/* ─── Connections (select-only; created + edited on the Factory page) ─────── */

function DestinationsSection() {
  const fab = useFabricationCtx();
  const navigate = useNavigate();

  // Load the shared connection list once (also feeds the Estimate / Open selects).
  // Connections are created + edited on the Factory page, not here.
  useEffect(() => {
    void fab.list();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="pb-1.5">
      {fab.destinations.length === 0 ? (
        <p className="px-3.5 pb-1.5 pt-2 text-caption text-ink-3">
          No connections yet. Set one up on the Factory page to send prints to your slicer.
        </p>
      ) : (
        <div className="flex flex-col">
          {fab.destinations.map((d) => (
            <div key={d.id} className="px-3.5 py-2">
              <p className="truncate text-body text-ink">{d.name}</p>
              {(d.printerProfile || d.filamentProfile || d.processProfile) && (
                <p className="truncate text-caption text-ink-3">
                  {[d.printerProfile, d.filamentProfile, d.processProfile]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={() => navigate("factory")}
        className="mx-2.5 my-1.5 inline-flex items-center gap-1.5 rounded-md border border-line-2 bg-surface px-2.5 py-1 text-caption font-medium text-ink-2 transition-colors hover:border-line-3 hover:text-ink"
      >
        <Factory size={13} strokeWidth={2} />
        Manage connections
      </button>
    </div>
  );
}

/* ─── Slice & estimate ───────────────────────────────────────────────────── */

function EstimateSection({ buildId }: { buildId: number }) {
  const fab = useFabricationCtx();
  const [destId, setDestId] = useState<string>("");

  const destOpts = [
    { value: "", label: "No destination (approx)" },
    ...fab.destinations.map((d) => ({ value: d.id, label: d.name })),
  ];

  const run = () => void fab.fetchEstimate(destId || null);

  const est = fab.estimate;

  return (
    <div className="pb-2 pt-1.5">
      {buildId < 0 ? (
        <p className="px-3.5 py-1.5 text-caption text-ink-3">Build a model to estimate.</p>
      ) : (
        <>
          <div className="flex items-center gap-2 px-3.5 pb-2">
            {fab.destinations.length > 0 && (
              <Select
                value={destId}
                onChange={setDestId}
                ariaLabel="Destination"
                className="min-w-0 flex-1"
                options={destOpts}
              />
            )}
            <button
              type="button"
              onClick={run}
              disabled={fab.loading}
              className="h-8.5 shrink-0 rounded-lg bg-accent px-3 text-caption font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {fab.loading ? "Running…" : "Estimate"}
            </button>
          </div>

          {est && (
            <div className="border-t border-line pt-1">
              {est.timeSeconds !== undefined ? (
                <Row k="Print time" v={fmtDuration(est.timeSeconds)} />
              ) : (
                <div className="flex items-center gap-2 px-3.5 py-1.5">
                  <span className="text-xs text-ink-3">Print time</span>
                  <span className="ml-auto text-right text-caption text-ink-3">
                    install a slicer for print time
                  </span>
                </div>
              )}
              {est.filamentGrams !== undefined && (
                <Row k="Filament" v={`${est.filamentGrams.toFixed(1)} g`} />
              )}
              {est.cost !== undefined && (
                <Row k="Cost" v={`${est.cost.toFixed(2)} ${est.currency}`} />
              )}
              {est.layerCount !== undefined && <Row k="Layers" v={String(est.layerCount)} />}
              {est.heightMm !== undefined && <Row k="Height" v={`${est.heightMm.toFixed(1)} mm`} />}
              {est.supportUsed !== undefined && (
                <Row k="Support" v={est.supportUsed ? "Yes" : "No"} />
              )}
              {est.fitsBed === false && (
                <div className="flex justify-between gap-3 px-3.5 py-1.5 text-xs">
                  <span className="shrink-0 text-ink-3">Bed fit</span>
                  <span className="min-w-0 truncate text-right font-mono text-amber">
                    Larger than the printer bed
                  </span>
                </div>
              )}
              {est.source === "approx" && (
                <p className="px-3.5 pb-1.5 pt-1 text-caption text-ink-3">
                  Geometric approximation. Figures improve with a connected slicer.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ─── Auto-orient ────────────────────────────────────────────────────────── */

function OrientSection({ buildId }: { buildId: number }) {
  const fab = useFabricationCtx();
  const result = fab.orient;

  const run = () => void fab.findOrientation();
  const saving = result ? supportSaving(result.supportArea, result.worstSupportArea) : 0;

  return (
    <div className="pb-2 pt-1.5">
      {buildId < 0 ? (
        <p className="px-3.5 py-1.5 text-caption text-ink-3">Build a model to find orientation.</p>
      ) : (
        <>
          <div className="flex items-center gap-2 px-3.5 pb-2">
            <p className="min-w-0 flex-1 text-caption text-ink-3">
              Finds the rotation that minimizes support material.
            </p>
            <button
              type="button"
              onClick={run}
              disabled={fab.loading}
              className="h-8.5 shrink-0 rounded-lg border border-line-2 bg-surface px-3 text-caption font-medium text-ink-2 transition-colors hover:border-line-3 hover:text-ink disabled:opacity-50"
            >
              {fab.loading ? "Running…" : "Analyze"}
            </button>
          </div>

          {result && (
            <div className="border-t border-line pt-1">
              <Row k="Rotation" v={result.rotation.map((n) => `${n.toFixed(1)}°`).join(", ")} />
              <Row k="Support area" v={`${result.supportArea.toFixed(1)} mm²`} />
              {saving > 0 && (
                <div className="flex items-center justify-between gap-3 px-3.5 py-1.5 text-xs">
                  <span className="shrink-0 text-ink-3">Improvement</span>
                  <span className="font-mono tabular-nums text-engine">
                    saves ~{saving}% support
                  </span>
                </div>
              )}
              <p className="px-3.5 pt-1 pb-1.5 text-caption text-ink-3">
                Suggested print orientation. Export the model to apply it.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ─── Open in OrcaSlicer ─────────────────────────────────────────────────── */

function OpenSection({ buildId }: { buildId: number }) {
  const fab = useFabricationCtx();
  const [destId, setDestId] = useState<string>("");

  if (!fab.install?.found) return null;

  const destOpts = [
    { value: "", label: "No destination" },
    ...fab.destinations.map((d) => ({ value: d.id, label: d.name })),
  ];

  const handleOpen = () => void fab.open(destId || null);

  return (
    <div className="border-t border-line px-3.5 py-3">
      {buildId < 0 ? (
        <p className="text-caption text-ink-3">Build a model to open it in OrcaSlicer.</p>
      ) : (
        <div className="flex items-center gap-2">
          {fab.destinations.length > 0 && (
            <Select
              value={destId}
              onChange={setDestId}
              ariaLabel="Destination"
              className="min-w-0 flex-1"
              options={destOpts}
            />
          )}
          <button
            type="button"
            onClick={handleOpen}
            disabled={fab.loading}
            className="inline-flex h-8.5 shrink-0 items-center gap-2 rounded-lg bg-accent px-3 text-caption font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            <Printer size={13} strokeWidth={2} />
            Open in OrcaSlicer
          </button>
        </div>
      )}
    </div>
  );
}

/* ─── Context — shares one useFabrication instance across sub-components ─── */

// We pass the fab state/actions down via a module-level singleton ref so that
// inner sections share one hook instance without prop-drilling through every
// level. The panel renders a single `<MakePanelInner>` once it has constructed
// the context value.

import { createContext, useContext } from "react";
import type { FabricationState } from "../../hooks/useFabrication";

const FabCtx = createContext<FabricationState | null>(null);

function useFabricationCtx(): FabricationState {
  const ctx = useContext(FabCtx);
  if (!ctx) throw new Error("useFabricationCtx used outside MakePanel");
  return ctx;
}

/* ─── panel ──────────────────────────────────────────────────────────────── */

export default function MakePanel({ buildId, active }: { buildId: number; active: boolean }) {
  const fab = useFabrication(buildId);
  const [open, setOpen] = useState({
    slicer: true,
    destinations: true,
    estimate: true,
    orient: false,
  });
  const toggle = (k: keyof typeof open) => setOpen((o) => ({ ...o, [k]: !o[k] }));

  return (
    <FabCtx.Provider value={fab}>
      <div className="pb-2">
        {fab.error && (
          <div className="flex items-center justify-between gap-2 border-b border-line px-3.5 py-2">
            <p className="text-caption text-ink-3">{fab.error}</p>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => {
                // Clear error by re-detecting — the hook will clear error on next call.
                void fab.detect();
              }}
              className="grid h-5 w-5 shrink-0 place-items-center rounded-sm text-ink-3 hover:bg-surface-2 hover:text-ink"
            >
              <X size={13} strokeWidth={2} />
            </button>
          </div>
        )}

        <CollapsibleSection title="Slicer" open={open.slicer} onToggle={() => toggle("slicer")}>
          <SlicerSection active={active && open.slicer} />
        </CollapsibleSection>

        <CollapsibleSection
          title="Destinations"
          count={fab.destinations.length || undefined}
          open={open.destinations}
          onToggle={() => toggle("destinations")}
        >
          <DestinationsSection />
        </CollapsibleSection>

        <CollapsibleSection
          title="Slice & estimate"
          open={open.estimate}
          onToggle={() => toggle("estimate")}
        >
          <EstimateSection buildId={buildId} />
        </CollapsibleSection>

        <CollapsibleSection
          title="Auto-orient"
          open={open.orient}
          onToggle={() => toggle("orient")}
        >
          <OrientSection buildId={buildId} />
        </CollapsibleSection>

        <OpenSection buildId={buildId} />
      </div>
    </FabCtx.Provider>
  );
}
