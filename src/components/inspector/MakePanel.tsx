/**
 * MakePanel — the Inspector's Make tab: one header block (slicer status, the
 * shared destination, and the OrcaSlicer handoff as the primary action) over
 * Estimate and Orientation sections. Destinations are created and edited on
 * the Factory page; the one picked here feeds every action below it.
 */
import { useEffect, useState } from "react";
import { Factory, Printer, RotateCw } from "lucide-react";
import { useNavigate } from "react-router-dom";

import CollapsibleSection from "./CollapsibleSection";
import Select from "../ui/Select";
import { useFabrication, type FabricationState } from "../../hooks/useFabrication";
import type { SectionKey, SectionState } from "../../state/useInspectorPrefs";

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

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 px-3.5 py-1.5 text-xs">
      <span className="shrink-0 text-ink-3">{k}</span>
      <span className="min-w-0 truncate text-right font-mono tabular-nums text-ink">{v}</span>
    </div>
  );
}

/* ─── header: slicer status + destination + handoff ─────────────────────── */

function SetupHeader({
  fab,
  buildId,
  destId,
  onDestChange,
}: {
  fab: FabricationState;
  buildId: number;
  destId: string;
  onDestChange: (id: string) => void;
}) {
  const navigate = useNavigate();
  const { install, loading } = fab;

  return (
    <div className="border-b border-line px-3.5 pb-3 pt-2.5">
      {/* slicer status line */}
      {loading && install === null ? (
        <p className="text-caption text-ink-3">Detecting slicer…</p>
      ) : install?.found ? (
        <div className="flex items-center justify-between gap-2">
          <p className="text-body text-ink">
            OrcaSlicer
            {install.version && (
              <span className="ml-1.5 font-mono text-caption text-ink-3">{install.version}</span>
            )}
          </p>
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
            Estimates below stay approximate until then.
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

      {/* shared destination — feeds the estimate and the handoff below */}
      <div className="mt-2.5 flex items-center gap-1.5">
        <Select
          value={destId}
          onChange={onDestChange}
          ariaLabel="Destination"
          className="min-w-0 flex-1"
          options={[
            {
              value: "",
              label: fab.destinations.length > 0 ? "No destination" : "No destinations yet",
            },
            ...fab.destinations.map((d) => ({ value: d.id, label: d.name })),
          ]}
        />
        <button
          type="button"
          onClick={() => navigate("factory")}
          title="Manage destinations on the Factory page"
          className="grid h-8.5 w-8.5 shrink-0 place-items-center rounded-lg border border-line-2 bg-surface text-ink-2 transition-colors hover:border-line-3 hover:text-ink"
        >
          <Factory size={14} strokeWidth={1.9} />
        </button>
      </div>

      {/* primary action: hand the model to the slicer */}
      {install?.found && (
        <button
          type="button"
          onClick={() => void fab.open(destId || null)}
          disabled={fab.loading || buildId < 0}
          title={buildId < 0 ? "Build a model first" : undefined}
          className="mt-2 inline-flex h-8.5 w-full items-center justify-center gap-2 rounded-lg bg-accent px-3 text-caption font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          <Printer size={13} strokeWidth={2} />
          Open in OrcaSlicer
        </button>
      )}
    </div>
  );
}

/* ─── Estimate ───────────────────────────────────────────────────────────── */

function EstimateSection({
  fab,
  buildId,
  destId,
}: {
  fab: FabricationState;
  buildId: number;
  destId: string;
}) {
  const est = fab.estimate;

  if (buildId < 0) {
    return (
      <p className="px-3.5 pb-2.5 pt-0.5 text-caption text-ink-3">Build a model to estimate.</p>
    );
  }

  return (
    <div className="pb-2 pt-0.5">
      <div className="flex items-center justify-between gap-2 px-3.5 pb-2">
        <p className="min-w-0 flex-1 text-caption text-ink-3">
          Print time, filament, and cost for the current model.
        </p>
        <button
          type="button"
          onClick={() => void fab.fetchEstimate(destId || null)}
          disabled={fab.loading}
          className="h-8.5 shrink-0 rounded-lg border border-line-2 bg-surface px-3 text-caption font-medium text-ink-2 transition-colors hover:border-line-3 hover:text-ink disabled:opacity-50"
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
          {est.cost !== undefined && <Row k="Cost" v={`${est.cost.toFixed(2)} ${est.currency}`} />}
          {est.layerCount !== undefined && <Row k="Layers" v={String(est.layerCount)} />}
          {est.heightMm !== undefined && <Row k="Height" v={`${est.heightMm.toFixed(1)} mm`} />}
          {est.supportUsed !== undefined && <Row k="Support" v={est.supportUsed ? "Yes" : "No"} />}
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
    </div>
  );
}

/* ─── Orientation ────────────────────────────────────────────────────────── */

function OrientSection({ fab, buildId }: { fab: FabricationState; buildId: number }) {
  const result = fab.orient;
  const saving = result ? supportSaving(result.supportArea, result.worstSupportArea) : 0;

  if (buildId < 0) {
    return (
      <p className="px-3.5 pb-2.5 pt-0.5 text-caption text-ink-3">
        Build a model to find its print orientation.
      </p>
    );
  }

  return (
    <div className="pb-2 pt-0.5">
      <div className="flex items-center justify-between gap-2 px-3.5 pb-2">
        <p className="min-w-0 flex-1 text-caption text-ink-3">
          Finds the rotation that minimizes support material.
        </p>
        <button
          type="button"
          onClick={() => void fab.findOrientation()}
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
              <span className="font-mono tabular-nums text-engine">saves ~{saving}% support</span>
            </div>
          )}
          <p className="px-3.5 pb-1.5 pt-1 text-caption text-ink-3">
            Suggested print orientation. Export the model to apply it.
          </p>
        </div>
      )}
    </div>
  );
}

/* ─── panel ──────────────────────────────────────────────────────────────── */

export default function MakePanel({
  buildId,
  active,
  open,
  onToggleSection,
}: {
  buildId: number;
  active: boolean;
  open: SectionState;
  onToggleSection: (k: SectionKey) => void;
}) {
  const fab = useFabrication(buildId);
  const [destId, setDestId] = useState("");

  // Detect the slicer + load destinations once the tab is first shown.
  useEffect(() => {
    if (!active) return;
    if (fab.install === null && !fab.loading) void fab.detect();
    void fab.list();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  return (
    <div className="pb-2">
      {fab.error && (
        <p className="border-b border-line px-3.5 py-2 text-caption text-ink-3">{fab.error}</p>
      )}

      <SetupHeader fab={fab} buildId={buildId} destId={destId} onDestChange={setDestId} />

      <CollapsibleSection
        title="Estimate"
        open={open["make.estimate"]}
        onToggle={() => onToggleSection("make.estimate")}
      >
        <EstimateSection fab={fab} buildId={buildId} destId={destId} />
      </CollapsibleSection>

      <CollapsibleSection
        title="Orientation"
        open={open["make.orient"]}
        onToggle={() => onToggleSection("make.orient")}
      >
        <OrientSection fab={fab} buildId={buildId} />
      </CollapsibleSection>
    </div>
  );
}
