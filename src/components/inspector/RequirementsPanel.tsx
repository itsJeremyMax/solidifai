/**
 * RequirementsPanel — the Inspector's Requirements tab. Goals as a live
 * checklist with pass/fail, regression badges, a richer predicate composer,
 * and a "Converge to spec" action for parametric models.
 */
import { useMemo, useState } from "react";
import { ArrowRight, ChevronDown, Plus, RefreshCw, X } from "lucide-react";

import Select from "../ui/Select";
import { useRequirements } from "../../hooks/useRequirements";
import { useConverge } from "../../hooks/useConverge";
import { engineSetParams } from "../../lib/ipc/engine";
import {
  OPS,
  PRESETS,
  QUANTITIES,
  isAssert,
  presetToRequirement,
  toRequirement,
  type Bound,
  type Delta,
  type Op,
  type Quantity,
  type Requirement,
  type RequirementResult,
  type VectorBound,
} from "../../lib/requirements";

/* ── helpers ─────────────────────────────────────────────────────────────── */

function statusDot(pass: boolean | null) {
  if (pass === true) return "bg-engine";
  if (pass === false) return "bg-danger-bold";
  return "border border-line-3";
}

function resultLine(r: RequirementResult): string {
  if (r.pass === null) return "Build to check";
  if (r.detail) return r.detail;
  if (r.pass === true) {
    if (r.quantity === "watertight") return "Watertight";
    if (r.quantity === "dfm_critical") return "No critical issues";
    if (r.quantity === "overlaps") return "No overlaps";
    if (r.measured !== null && r.unit)
      return `${
        Array.isArray(r.measured)
          ? (r.measured as number[]).map((v) => v.toFixed(1)).join(" × ")
          : r.measured
      } ${r.unit}`;
  }
  return "";
}

function DeltaBadge({ delta }: { delta?: Delta }) {
  if (!delta || delta === "unchanged" || delta === "new") return null;
  const isRegressed = delta === "regressed";
  return (
    <span
      className={`ml-1 rounded px-1.25 py-0.25 font-mono text-micro font-semibold uppercase tracking-eyebrow ${
        isRegressed ? "bg-amber/12 text-amber" : "bg-engine/12 text-engine"
      }`}
    >
      {isRegressed ? "regressed" : "fixed"}
    </span>
  );
}

/* ── goal row ────────────────────────────────────────────────────────────── */

function GoalRow({ r, onRemove }: { r: RequirementResult; onRemove: () => void }) {
  return (
    <div className="group flex items-start gap-2.5 px-3.5 py-2">
      <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${statusDot(r.pass)}`} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-0.5 text-body text-ink">
          {r.label}
          <DeltaBadge delta={r.delta} />
          {r.lowTrust && (
            <span className="ml-1 rounded px-1 py-0.25 font-mono text-micro text-ink-3">~</span>
          )}
        </span>
        <span className="mt-0.5 block font-mono text-caption text-ink-3">{resultLine(r)}</span>
      </span>
      <button
        type="button"
        onClick={onRemove}
        title="Remove goal"
        aria-label={`Remove ${r.label}`}
        className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-sm text-ink-3 opacity-0 transition hover:bg-surface-2 hover:text-ink group-hover:opacity-100"
      >
        <X size={13} strokeWidth={2} />
      </button>
    </div>
  );
}

/* ── composer ────────────────────────────────────────────────────────────── */

const COMPOSABLE_QUANTITIES = QUANTITIES.filter(
  (q) => q.targetKind !== "none" || ["dfm_critical", "overlaps", "watertight"].includes(q.quantity),
);

function defaultBoundFor(quantity: Quantity, op: Op): Bound {
  if (quantity === "watertight") return true;
  if (quantity === "dfm_critical" || quantity === "overlaps") return 0;
  if (quantity === "size") return [60, 40, 20] as VectorBound;
  if (op === "within") return [1.0, 2.0];
  if (quantity === "mass") return op === "<=" ? 50 : 10;
  return 1.0;
}

function defaultOpFor(quantity: Quantity): Op {
  if (quantity === "watertight") return "==";
  if (quantity === "dfm_critical" || quantity === "overlaps") return "<=";
  if (quantity === "min_wall" || quantity === "min_clearance" || quantity === "mass")
    return quantity === "mass" ? "<=" : ">=";
  return "<=";
}

function Composer({ onAdd }: { onAdd: (r: Requirement) => void }) {
  const [open, setOpen] = useState(false);
  const [quantity, setQuantity] = useState<Quantity>("mass");
  const [op, setOp] = useState<Op>("<=");

  const qMeta = QUANTITIES.find((q) => q.quantity === quantity)!;
  const isBooleanTarget =
    quantity === "watertight" || quantity === "dfm_critical" || quantity === "overlaps";
  const isVector = qMeta.targetKind === "vector";
  const isRange = op === "within" && !isBooleanTarget && !isVector;

  const [scalar, setScalar] = useState(50);
  const [range, setRange] = useState<[number, number]>([1.0, 2.0]);
  const [vector, setVector] = useState<VectorBound>([60, 40, 20]);

  const changeQuantity = (q: Quantity) => {
    setQuantity(q);
    const nextOp = defaultOpFor(q);
    setOp(nextOp);
    const def = defaultBoundFor(q, nextOp);
    if (typeof def === "number") setScalar(def);
    else if (Array.isArray(def) && def.length === 2) setRange(def as [number, number]);
    else if (Array.isArray(def) && def.length === 3) setVector(def as VectorBound);
  };

  const submit = () => {
    let bound: Bound;
    if (isBooleanTarget) {
      bound = quantity === "watertight" ? true : 0;
    } else if (isVector) {
      bound = vector;
    } else if (isRange) {
      bound = range;
    } else {
      bound = scalar;
    }
    onAdd({ id: crypto.randomUUID(), quantity, op, bound, enabled: true });
    setOpen(false);
  };

  if (!open) {
    return (
      <div className="mx-2.5 mb-2 mt-1">
        {/* preset chips */}
        <div className="mb-2 flex flex-wrap gap-1">
          {PRESETS.map((p) => (
            <button
              key={p.type}
              type="button"
              onClick={() => onAdd(presetToRequirement(p.type))}
              title={`Add: ${p.label}`}
              className="inline-flex items-center gap-1 rounded-md border border-line-2 bg-surface px-2 py-0.75 text-caption text-ink-2 transition-colors hover:border-line-3 hover:text-ink"
            >
              <Plus size={10} strokeWidth={2.5} />
              {p.label}
            </button>
          ))}
        </div>
        {/* compose custom */}
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex items-center gap-1.5 text-caption text-ink-3 transition-colors hover:text-ink"
        >
          <ChevronDown size={12} strokeWidth={2} />
          Custom goal
        </button>
      </div>
    );
  }

  return (
    <div className="m-2.5 flex flex-col gap-2 rounded-lg border border-line-2 bg-surface-2 p-2.5">
      {/* quantity */}
      <Select
        value={quantity}
        ariaLabel="Quantity"
        options={COMPOSABLE_QUANTITIES.map((q) => ({ value: q.quantity, label: q.label }))}
        onChange={(v) => changeQuantity(v as Quantity)}
      />

      {/* op (not shown for boolean targets) */}
      {!isBooleanTarget && (
        <Select
          value={op}
          ariaLabel="Operator"
          options={OPS.filter((o) => !(isVector && (o.op === "within" || o.op === "=="))).map(
            (o) => ({ value: o.op, label: o.label }),
          )}
          onChange={(v) => setOp(v as Op)}
        />
      )}

      {/* bound input(s) */}
      {!isBooleanTarget && !isVector && !isRange && (
        <label className="flex items-center gap-2 text-caption text-ink-3">
          <span className="w-14">{qMeta.unit ?? "value"}</span>
          <input
            type="number"
            min={0}
            step={0.1}
            value={scalar}
            onChange={(e) => setScalar(parseFloat(e.target.value))}
            className="h-8.5 w-24 rounded-lg border border-line-2 bg-surface px-2.5 font-mono text-caption text-ink transition-colors hover:border-line-3 focus:border-accent-line focus:outline-none"
          />
        </label>
      )}

      {isRange && (
        <div className="flex items-center gap-1.5 text-caption text-ink-3">
          <input
            type="number"
            min={0}
            step={0.1}
            value={range[0]}
            aria-label="Lower bound"
            onChange={(e) => setRange([parseFloat(e.target.value), range[1]])}
            className="h-8.5 w-full min-w-0 rounded-lg border border-line-2 bg-surface px-2 text-center font-mono text-caption text-ink transition-colors hover:border-line-3 focus:border-accent-line focus:outline-none"
          />
          <span className="shrink-0">to</span>
          <input
            type="number"
            min={0}
            step={0.1}
            value={range[1]}
            aria-label="Upper bound"
            onChange={(e) => setRange([range[0], parseFloat(e.target.value)])}
            className="h-8.5 w-full min-w-0 rounded-lg border border-line-2 bg-surface px-2 text-center font-mono text-caption text-ink transition-colors hover:border-line-3 focus:border-accent-line focus:outline-none"
          />
          <span className="shrink-0">{qMeta.unit ?? ""}</span>
        </div>
      )}

      {isVector && (
        <div className="flex items-center gap-1.5">
          {(["X", "Y", "Z"] as const).map((axis, i) => (
            <input
              key={axis}
              type="number"
              min={0}
              step={1}
              aria-label={`${axis} mm`}
              value={vector[i]}
              onChange={(e) => {
                const next = [...vector] as VectorBound;
                next[i] = parseFloat(e.target.value);
                setVector(next);
              }}
              className="h-8.5 w-full min-w-0 rounded-lg border border-line-2 bg-surface px-1.5 text-center font-mono text-caption text-ink transition-colors hover:border-line-3 focus:border-accent-line focus:outline-none"
            />
          ))}
          <span className="shrink-0 text-caption text-ink-3">mm</span>
        </div>
      )}

      <div className="flex items-center justify-end gap-1.5">
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded-md px-2 py-1 text-caption text-ink-3 transition-colors hover:text-ink"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={submit}
          className="rounded-md bg-accent px-2.5 py-1 text-caption font-semibold text-white transition-opacity hover:opacity-90"
        >
          Add
        </button>
      </div>
    </div>
  );
}

/* ── converge result panel ───────────────────────────────────────────────── */

interface ConvergePanelProps {
  result: import("../../lib/requirements").ConvergeResult;
  onApply: (params: Record<string, number>) => Promise<void>;
  onDismiss: () => void;
  applying: boolean;
}

function ConvergePanel({ result, onApply, onDismiss, applying }: ConvergePanelProps) {
  if (!result.found) {
    return (
      <div className="mx-2.5 mb-2 rounded-lg border border-line-2 bg-surface-2 p-3">
        <p className="mb-1.5 text-caption font-medium text-ink">
          No parameter combination meets all goals.
        </p>
        {result.closestMiss && (
          <p className="mb-1 text-caption text-ink-3">
            The closest candidate still had unmet goals. Try asking the agent to adjust the model
            geometry using the <span className="font-mono">solidifai-converge</span> skill.
          </p>
        )}
        {result.notAddressable.length > 0 && (
          <p className="text-caption text-ink-3">
            These goals need geometry changes, not parameter tuning:{" "}
            <span className="font-medium text-ink">
              {result.notAddressable.map((g) => g.label).join(", ")}.
            </span>
          </p>
        )}
        <div className="mt-2.5 flex justify-end">
          <button
            type="button"
            onClick={onDismiss}
            className="rounded-md px-2 py-1 text-caption text-ink-3 transition-colors hover:text-ink"
          >
            Dismiss
          </button>
        </div>
      </div>
    );
  }

  const params = result.params ?? {};
  const paramKeys = Object.keys(params);

  return (
    <div className="mx-2.5 mb-2 rounded-lg border border-line-2 bg-surface-2 p-3">
      <p className="mb-2 text-caption font-medium text-ink">
        Found settings that meet all goals
        {result.evaluated > 0 && (
          <span className="ml-1 font-normal text-ink-3">
            ({result.evaluated} combinations checked)
          </span>
        )}
      </p>

      {/* proposed param changes */}
      {paramKeys.length > 0 && (
        <div className="mb-2.5 flex flex-wrap gap-1.5">
          {paramKeys.map((k) => (
            <span
              key={k}
              className="inline-flex items-center gap-1 rounded-md bg-accent-bg px-2 py-0.75 font-mono text-caption text-accent"
            >
              {k} = {params[k]}
            </span>
          ))}
        </div>
      )}

      {/* before / after per goal */}
      {result.before.length > 0 && result.after && (
        <div className="mb-2.5 flex flex-col gap-1">
          {result.before.map((b, i) => {
            const a = result.after?.[i];
            const improved = a && b.pass === false && a.pass === true;
            return (
              <div key={b.id} className="flex items-center gap-1.5 text-caption">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    b.pass === true ? "bg-engine" : "bg-danger-bold"
                  }`}
                />
                <span className="text-ink-3">{b.label}</span>
                {a && (
                  <>
                    <ArrowRight size={10} strokeWidth={2} className="text-ink-3" />
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        a.pass === true ? "bg-engine" : "bg-danger-bold"
                      }`}
                    />
                    {improved && (
                      <span className="font-mono text-micro font-semibold uppercase tracking-eyebrow text-engine">
                        fixed
                      </span>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* notAddressable note */}
      {result.notAddressable.length > 0 && (
        <p className="mb-2 text-caption text-ink-3">
          These goals need geometry changes:{" "}
          <span className="font-medium text-ink">
            {result.notAddressable.map((g) => g.label).join(", ")}.
          </span>
        </p>
      )}

      <div className="flex items-center justify-end gap-1.5">
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-md px-2 py-1 text-caption text-ink-3 transition-colors hover:text-ink"
        >
          Dismiss
        </button>
        <button
          type="button"
          onClick={() => void onApply(params)}
          disabled={applying || paramKeys.length === 0}
          className="inline-flex items-center gap-1.5 rounded-md bg-accent px-2.5 py-1 text-caption font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {applying ? (
            <>
              <RefreshCw size={11} strokeWidth={2} className="animate-spin" />
              Applying
            </>
          ) : (
            "Apply"
          )}
        </button>
      </div>
    </div>
  );
}

/* ── panel ───────────────────────────────────────────────────────────────── */

export default function RequirementsPanel({
  buildId,
  active,
  hasParams = false,
}: {
  buildId: number;
  active: boolean;
  /** True when the model declares at least one adjustable parameter (PARAMS). */
  hasParams?: boolean;
}) {
  const { report, loading, setRequirements } = useRequirements(buildId, active);
  const {
    run: convergeRun,
    result: convergeResult,
    loading: converging,
    clear: convergeClear,
  } = useConverge(buildId);
  const [applying, setApplying] = useState(false);

  const current = useMemo<Requirement[]>(
    () =>
      (report?.requirements ?? []).map((r) => toRequirement(r)).filter((r) => !isAssert(r) || true),
    [report],
  );

  const add = (r: Requirement) => void setRequirements([...current, r]);
  const remove = (id: string) => void setRequirements(current.filter((r) => r.id !== id));

  const summary = report?.summary;
  const hasGoals = (report?.requirements.length ?? 0) > 0;
  const hasUnmet = hasGoals && summary && !summary.allMet;

  // Show converge button: parametric model + at least one unmet goal.
  const showConvergeBtn = hasParams && hasUnmet && !convergeResult && !converging;

  const applyConvergeParams = async (params: Record<string, number>) => {
    setApplying(true);
    await engineSetParams(params);
    convergeClear();
    setApplying(false);
  };

  return (
    <div className="pb-2">
      {/* summary strip */}
      {hasGoals && summary && (
        <div className="flex items-center gap-3 border-b border-line px-3.5 py-2.5">
          <span
            className={`inline-flex items-center gap-1.5 text-caption ${
              summary.allMet ? "text-engine" : "text-ink-2"
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${summary.allMet ? "bg-engine" : "bg-amber"}`} />
            {summary.met} / {summary.total} met
          </span>
          {!!summary.regressed && summary.regressed > 0 && (
            <span className="text-caption text-amber">{summary.regressed} regressed</span>
          )}
          {!!summary.fixed && summary.fixed > 0 && (
            <span className="text-caption text-engine">{summary.fixed} fixed</span>
          )}
        </div>
      )}

      {/* goal rows */}
      {report?.requirements.map((r) => (
        <GoalRow key={r.id} r={r} onRemove={() => remove(r.id)} />
      ))}

      {/* empty state */}
      {!hasGoals && (
        <p className="px-3.5 pb-1 pt-3.5 text-body text-ink-3">
          {loading
            ? "Loading goals..."
            : "Set a goal (max mass, fits a box, printable) and watch it verify on every build."}
        </p>
      )}

      {/* converge action */}
      {showConvergeBtn && (
        <div className="mx-2.5 mb-1 mt-0.5">
          <button
            type="button"
            onClick={() => void convergeRun()}
            className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-accent-line bg-accent-bg px-3 py-2 text-caption font-medium text-accent transition-colors hover:bg-accent/14"
          >
            <RefreshCw size={12} strokeWidth={2} />
            Converge to spec
          </button>
        </div>
      )}

      {/* converge loading */}
      {converging && (
        <div className="mx-2.5 mb-1 mt-0.5 flex items-center gap-1.5 rounded-lg border border-line-2 bg-surface-2 px-3 py-2 text-caption text-ink-3">
          <RefreshCw size={12} strokeWidth={2} className="animate-spin" />
          Searching parameter space...
        </div>
      )}

      {/* converge result */}
      {convergeResult && (
        <ConvergePanel
          result={convergeResult}
          onApply={applyConvergeParams}
          onDismiss={convergeClear}
          applying={applying}
        />
      )}

      <Composer onAdd={add} />
    </div>
  );
}
