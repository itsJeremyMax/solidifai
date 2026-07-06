/**
 * ManufacturingProfile — the "Manufacturing" settings section.
 *
 * Edits the manufacturing profile Sol builds to: design defaults, fit clearances,
 * the print/cut process, and advisory fabrication values. An in-panel scope
 * toggle (Global | This workspace) picks the layer being edited; workspace fields
 * fall back to the global profile, and every field shows whether it is set here or
 * inherited, with a one-click reset back to the inherited value. The default
 * material is echoed read-only (it is owned by the Materials library).
 *
 * Every change auto-saves through the optimistic `useManufacturingProfile` hook;
 * Rust is the sole writer of the profile on disk.
 */
import { useEffect, useState } from "react";

import Select from "../ui/Select";
import { getActiveWorkspace } from "../../lib/workspaces";
import { useManufacturingProfile, type Scope } from "../../hooks/useManufacturingProfile";

const INPUT =
  "h-8.5 w-24 rounded-lg border border-line-2 bg-surface-2 px-2.75 text-right text-body text-ink outline-none transition-colors duration-150 focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent-tint";

type Num = { section: string; key: string; label: string; unit: string };
const GROUPS: { title: string; note?: string; nums?: Num[]; custom?: "fit" | "method" }[] = [
  {
    title: "Design",
    custom: "fit",
    nums: [
      { section: "design", key: "wallMm", label: "Wall thickness", unit: "mm" },
      { section: "design", key: "filletMm", label: "Edge break", unit: "mm" },
      { section: "design", key: "minFeatureMm", label: "Min feature", unit: "mm" },
    ],
  },
  {
    title: "Clearances",
    note: "per fit class",
    nums: [
      { section: "fits", key: "looseMm", label: "Loose", unit: "mm" },
      { section: "fits", key: "normalMm", label: "Normal", unit: "mm" },
      { section: "fits", key: "tightMm", label: "Tight", unit: "mm" },
    ],
  },
  {
    title: "Process",
    custom: "method",
    nums: [
      { section: "process", key: "nozzleMm", label: "Nozzle", unit: "mm" },
      { section: "process", key: "layerMm", label: "Layer height", unit: "mm" },
      { section: "process", key: "overhangDeg", label: "Overhang", unit: "deg" },
      { section: "process", key: "infillPct", label: "Infill", unit: "%" },
    ],
  },
  {
    title: "Fabrication",
    note: "advisory; the slicer owns the real values",
    nums: [
      { section: "fabrication", key: "nozzleTempC", label: "Nozzle temp", unit: "C" },
      { section: "fabrication", key: "bedTempC", label: "Bed temp", unit: "C" },
      { section: "fabrication", key: "filamentCostPerKg", label: "Filament cost", unit: "/kg" },
    ],
  },
];

export default function ManufacturingProfile() {
  const [hasWorkspace, setHasWorkspace] = useState(false);
  const [scope, setScope] = useState<Scope>("global");
  const [ready, setReady] = useState(false);

  // Default to the focused workspace when one is open, else the global profile.
  useEffect(() => {
    let live = true;
    getActiveWorkspace().then((ws) => {
      if (!live) return;
      setHasWorkspace(!!ws);
      setScope(ws ? "workspace" : "global");
      setReady(true);
    });
    return () => {
      live = false;
    };
  }, []);

  if (!ready) return <div className="mx-auto max-w-160 py-6.5 text-body text-ink-3">Loading…</div>;
  // Remount on scope flip so the hook reloads the right layer cleanly.
  return <Panel key={scope} scope={scope} hasWorkspace={hasWorkspace} setScope={setScope} />;
}

function Panel({
  scope,
  hasWorkspace,
  setScope,
}: {
  scope: Scope;
  hasWorkspace: boolean;
  setScope: (s: Scope) => void;
}) {
  const { view, loading, error, setField, resetField } = useManufacturingProfile(scope);
  // "Set here" means this layer carries the override (vs inheriting it).
  const isSet = (section: string, key: string) => view.overrides?.[section]?.[key] !== undefined;

  return (
    <div className="mx-auto max-w-160 py-6.5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold tracking-snug text-ink">Manufacturing</h2>
          <p className="mt-1.25 text-body leading-normal text-ink-2">
            {scope === "workspace"
              ? "Defaults for parts in this workspace. Blank fields inherit your global profile."
              : "Global defaults Sol builds to. Each workspace can override these."}
          </p>
        </div>
        <ScopeToggle scope={scope} hasWorkspace={hasWorkspace} onChange={setScope} />
      </div>

      {loading ? (
        <div className="mt-4.5 text-body text-ink-3">Loading…</div>
      ) : (
        <>
          <div className="mt-4 flex items-center gap-2 rounded-panel border border-line bg-surface px-4 py-2.5 text-body">
            <span className="text-ink-3">Default material</span>
            <span className="font-medium text-ink">{view.material.label || "—"}</span>
            <span className="ml-auto text-caption text-ink-3">set in Materials</span>
          </div>

          {error && (
            <div className="mt-3 rounded-lg border border-danger-line bg-danger-bg px-3 py-2 text-caption text-danger">
              {error}
            </div>
          )}

          {GROUPS.map((g) => (
            <section
              key={g.title}
              className="mt-4 overflow-hidden rounded-panel border border-line bg-surface"
            >
              <div className="border-b border-line px-4 py-2 text-micro uppercase tracking-eyebrow text-ink-3">
                {g.title}
                {g.note && (
                  <span className="ml-1.5 normal-case tracking-normal text-ink-3/70">{g.note}</span>
                )}
              </div>
              {g.custom === "fit" && (
                <FitRow
                  value={String(view.resolved?.design?.fit ?? "normal")}
                  set={isSet("design", "fit")}
                  onChange={(v) => setField("design", "fit", v)}
                  onReset={() => resetField("design", "fit")}
                />
              )}
              {g.custom === "method" && (
                <SelectRow
                  label="Method"
                  value={String(view.resolved?.process?.kind ?? "fdm")}
                  options={["fdm", "sla", "sls", "cnc"]}
                  set={isSet("process", "kind")}
                  onChange={(v) => setField("process", "kind", v)}
                  onReset={() => resetField("process", "kind")}
                />
              )}
              {g.nums?.map((n) => (
                <NumRow
                  key={`${n.section}.${n.key}`}
                  num={n}
                  value={view.resolved?.[n.section]?.[n.key]}
                  set={isSet(n.section, n.key)}
                  onCommit={(v) => setField(n.section, n.key, v)}
                  onReset={() => resetField(n.section, n.key)}
                />
              ))}
            </section>
          ))}
          <p className="mt-3 text-caption text-ink-3">
            Changes save automatically. Reset drops an override and falls back to the inherited
            value.
          </p>
        </>
      )}
    </div>
  );
}

/** A pill marking whether a field is overridden here or inherited from above. */
function Tag({ set }: { set: boolean }) {
  return set ? (
    <span className="rounded-full bg-accent-tint px-2 py-0.5 text-micro text-accent">set here</span>
  ) : (
    <span className="rounded-full bg-surface-2 px-2 py-0.5 text-micro text-ink-3">inherited</span>
  );
}

/** The trailing tag + (when overridden) reset control shared by every row. */
function RowTrail({ set, onReset }: { set: boolean; onReset: () => void }) {
  return (
    <span className="ml-auto flex items-center gap-2">
      <Tag set={set} />
      {set && (
        <button
          type="button"
          onClick={onReset}
          className="text-caption text-danger hover:underline"
        >
          reset
        </button>
      )}
    </span>
  );
}

function NumRow({
  num,
  value,
  set,
  onCommit,
  onReset,
}: {
  num: Num;
  value: number | string | undefined;
  set: boolean;
  onCommit: (v: number) => void;
  onReset: () => void;
}) {
  // Local draft so typing is unfettered; commit only on blur (one save per edit).
  const [draft, setDraft] = useState(String(value ?? ""));
  useEffect(() => {
    setDraft(String(value ?? ""));
  }, [value]);
  return (
    <div className="flex items-center gap-3 px-4 py-2">
      <label htmlFor={`${num.section}-${num.key}`} className="w-40 text-body text-ink-2">
        {num.label}
      </label>
      <input
        id={`${num.section}-${num.key}`}
        aria-label={num.label}
        inputMode="decimal"
        className={INPUT}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          const n = Number(draft);
          // Skip empty/blank (Number("") is 0), invalid, and no-op edits — a stray
          // 0 wall/clearance is dangerous, and a redundant write flips the view.
          if (draft.trim() === "" || Number.isNaN(n) || n === Number(value)) {
            setDraft(String(value ?? "")); // restore on empty/invalid/no-op
            return;
          }
          onCommit(n);
        }}
      />
      <span className="w-8 text-caption text-ink-3">{num.unit}</span>
      <RowTrail set={set} onReset={onReset} />
    </div>
  );
}

function SelectRow({
  label,
  value,
  options,
  set,
  onChange,
  onReset,
}: {
  label: string;
  value: string;
  options: string[];
  set: boolean;
  onChange: (v: string) => void;
  onReset: () => void;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-2">
      <span className="w-40 text-body text-ink-2">{label}</span>
      <Select
        className="w-32"
        ariaLabel={label}
        value={value}
        onChange={(v) => v !== value && onChange(v)}
        options={options.map((o) => ({ value: o, label: o.toUpperCase() }))}
      />
      <RowTrail set={set} onReset={onReset} />
    </div>
  );
}

function FitRow({
  value,
  set,
  onChange,
  onReset,
}: {
  value: string;
  set: boolean;
  onChange: (v: string) => void;
  onReset: () => void;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-2">
      <span className="w-40 text-body text-ink-2">Fit</span>
      <div
        role="group"
        aria-label="Fit"
        className="flex gap-0.5 rounded-[10px] border border-line-2 bg-surface-2 p-0.75"
      >
        {["loose", "normal", "tight"].map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => f !== value && onChange(f)}
            aria-pressed={value === f}
            className={`rounded-[7px] px-3 py-1.5 text-caption transition duration-150 ease-out-soft ${
              value === f
                ? "bg-surface font-semibold text-ink shadow-[0_1px_2px_rgba(16,18,24,.1)]"
                : "font-medium text-ink-2 hover:text-ink"
            }`}
          >
            {f[0].toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>
      <RowTrail set={set} onReset={onReset} />
    </div>
  );
}

function ScopeToggle({
  scope,
  hasWorkspace,
  onChange,
}: {
  scope: Scope;
  hasWorkspace: boolean;
  onChange: (s: Scope) => void;
}) {
  const opt = (s: Scope, label: string, disabled = false, title?: string) => (
    <button
      type="button"
      disabled={disabled}
      title={title}
      onClick={() => onChange(s)}
      className={`px-3 py-1.5 text-caption transition duration-150 ease-out-soft ${
        scope === s ? "bg-accent font-medium text-white" : "text-ink-3 disabled:opacity-40"
      }`}
    >
      {label}
    </button>
  );
  return (
    <div
      role="group"
      aria-label="Profile scope"
      className="flex shrink-0 overflow-hidden rounded-lg border border-line-2 text-caption"
    >
      {opt("global", "Global")}
      {opt(
        "workspace",
        "This workspace",
        !hasWorkspace,
        !hasWorkspace ? "Open a workspace to edit its profile" : undefined,
      )}
    </div>
  );
}
