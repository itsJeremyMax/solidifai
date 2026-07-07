/**
 * ExportDialog — format rail on the left, per-format options on the right with niche knobs behind an Advanced disclosure.
 */
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  Box,
  Layers,
  Globe,
  Grid3x3,
  Boxes,
  FileText,
  Download,
  X,
  Settings2,
  Check,
  ChevronDown,
} from "lucide-react";

import {
  FORMATS,
  UNIT_OPTIONS,
  PRECISION_OPTIONS,
  MESH_TYPE_OPTIONS,
  defaultOptions,
  qualityTolerance,
  type ExportOptions,
} from "../lib/exportSchema";
import {
  FieldRow,
  Segmented,
  FieldSelect,
  Toggle,
  NumberField,
  TextField,
  QualityPreset,
} from "./export/fields";
import { getWorkspaceDir } from "../lib/ipc/workspace";
import { tildePath } from "../lib/workspaces";

const GLYPH: Record<string, React.ReactNode> = {
  step: <Box size={16} strokeWidth={1.6} />,
  stl: <Layers size={16} strokeWidth={1.6} />,
  glb: <Globe size={16} strokeWidth={1.6} />,
  brep: <Grid3x3 size={16} strokeWidth={1.6} />,
  "3mf": <Boxes size={16} strokeWidth={1.6} />,
};

export interface ExportRequest {
  /** engine format string ("glb" or "gltf" after the container choice) */
  formatKey: string;
  ext: string;
  options: ExportOptions;
}

export default function ExportDialog({
  onExport,
  onClose,
}: {
  onExport: (req: ExportRequest) => void;
  onClose: () => void;
}) {
  const [sel, setSel] = useState("step");
  // one options object per format, lazily seeded from defaults
  const [byFmt, setByFmt] = useState<Record<string, ExportOptions>>({});
  // glTF container choice: "glb" (binary) or "gltf" (text)
  const [container, setContainer] = useState<"glb" | "gltf">("glb");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  // The default save location: the workspace's exports/ folder. Resolved once on
  // open, purely for the footer preview (the native Save dialog lets the user
  // pick elsewhere). Falls back to "exports/" while loading or outside a workspace.
  const [workspaceDir, setWorkspaceDir] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    getWorkspaceDir()
      .then((d) => {
        if (alive) setWorkspaceDir(d);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const fmt = FORMATS.find((f) => f.key === sel)!;
  const opts = byFmt[sel] ?? defaultOptions(sel);

  function set(patch: ExportOptions) {
    setByFmt((m) => ({ ...m, [sel]: { ...opts, ...patch } }));
  }
  function pickQuality(q: "draft" | "standard" | "fine") {
    const tolField = sel === "stl" ? "tolerance" : "linear_deflection";
    set({ quality: q, [tolField]: qualityTolerance(sel, q) });
  }

  const ext = sel === "glb" ? container : fmt.ext;
  const filename = `model.${ext}`;
  const dirDisplay = workspaceDir ? `${tildePath(workspaceDir)}/exports` : "exports";

  const request = useMemo<ExportRequest>(() => {
    const formatKey = sel === "glb" ? container : sel;
    return { formatKey, ext, options: opts };
  }, [sel, container, ext, opts]);

  return createPortal(
    <div className="fixed inset-0 z-50 grid place-items-center bg-scrim p-6" onClick={onClose}>
      <div
        className="animate-rise w-180 max-w-full overflow-hidden rounded-panel border border-line-2 bg-surface shadow-float"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.75 px-5 pt-4.5 pb-3.5">
          <span className="grid h-7.5 w-7.5 place-items-center rounded-lg bg-accent-tint text-accent">
            <Download size={17} strokeWidth={1.7} />
          </span>
          <div className="font-semibold tracking-snug text-ink">
            Export model
            <span className="block text-caption font-normal text-ink-3">
              Choose a format and tune the options.
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="ml-auto grid h-7 w-7 place-items-center rounded-md text-ink-3 hover:bg-surface-2 hover:text-ink-2"
          >
            <X size={15} strokeWidth={1.8} />
          </button>
        </div>
        <div className="h-px bg-line" />

        <div className="grid grid-cols-[228px_1fr]">
          <div
            className="rounded-bl-panel border-r border-line bg-surface-2 p-2.5"
            role="listbox"
            aria-label="Export format"
          >
            <div className="px-2 pb-2 pt-1.5 text-micro font-bold uppercase tracking-eyebrow text-ink-3">
              3D formats
            </div>
            {FORMATS.map((f) => (
              <button
                key={f.key}
                type="button"
                role="option"
                aria-selected={sel === f.key}
                onClick={() => {
                  setSel(f.key);
                  setAdvancedOpen(false);
                }}
                className={`flex w-full items-center gap-2.5 rounded-lg border px-2.25 py-2 text-left transition-colors duration-150 ${
                  sel === f.key
                    ? "border-line-2 bg-surface shadow-card"
                    : "border-transparent hover:bg-surface"
                }`}
              >
                <span
                  className={`grid h-7.5 w-7.5 flex-none place-items-center rounded-lg border ${
                    sel === f.key
                      ? "border-transparent bg-accent-tint text-accent"
                      : "border-line-2 bg-surface-2 text-ink-2"
                  }`}
                >
                  {GLYPH[f.key]}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-body font-semibold text-ink">{f.label}</span>
                  <span className="block truncate text-micro text-ink-3">{f.blurb}</span>
                </span>
                {sel === f.key ? (
                  <Check size={15} strokeWidth={2.2} className="ml-auto text-accent" />
                ) : null}
              </button>
            ))}
            <div className="px-2 pb-1 pt-3 text-micro font-bold uppercase tracking-eyebrow text-ink-3">
              2D drawings
            </div>
            <div className="flex items-center gap-2.5 rounded-lg px-2.25 py-2 opacity-50">
              <span className="grid h-7.5 w-7.5 flex-none place-items-center rounded-lg border border-line-2 bg-surface-2 text-ink-3">
                <FileText size={16} strokeWidth={1.6} />
              </span>
              <span>
                <span className="block text-body font-semibold text-ink-3">SVG, DXF</span>
                <span className="block text-micro text-ink-3">needs a 2D view</span>
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-4.5 p-5.5">
            <div>
              <div className="text-[15px] font-semibold tracking-snug text-ink">{fmt.label}</div>
              <div className="mt-0.75 max-w-[42ch] text-caption text-ink-2">{fmt.blurb}</div>
            </div>

            {fmt.exact ? (
              <div className="flex flex-col items-start gap-3 py-2">
                <span className="inline-flex h-5.5 items-center gap-1.5 rounded-md bg-[rgba(25,169,87,.12)] px-2.5 text-caption font-semibold text-engine">
                  <Check size={13} strokeWidth={2.2} /> Exact geometry. No settings to adjust.
                </span>
                <p className="max-w-[46ch] text-caption leading-relaxed text-ink-3">
                  BREP writes OpenCASCADE native geometry verbatim, so units, tolerance, and curves
                  are carried losslessly. Best for round-tripping back into build123d, CadQuery, or
                  FreeCAD.
                </p>
              </div>
            ) : (
              <>
                {renderEssentials()}
                {renderAdvanced()}
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2.5 border-t border-line px-5 py-3.5">
          <div
            className="flex h-8.5 min-w-0 flex-1 items-center overflow-hidden rounded-lg border border-line-2 bg-surface-2 px-2.5 font-mono text-caption"
            title={`${dirDisplay}/${filename}`}
          >
            <span className="truncate text-ink-3">{dirDisplay}/</span>
            <span className="flex-none text-ink">{filename}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-8.5 rounded-lg border border-line-2 bg-surface px-3.5 text-body font-medium text-ink-2 hover:border-line-3 hover:text-ink"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onExport(request)}
            className="inline-flex h-8.5 items-center gap-1.75 rounded-lg border border-transparent bg-accent px-3.5 text-body font-medium text-white shadow-[0_1px_1px_rgba(27,73,201,.4),inset_0_1px_0_rgba(255,255,255,.25)] hover:bg-accent-press"
          >
            <Download size={15} strokeWidth={1.8} /> Export
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );

  function renderEssentials() {
    if (sel === "step") {
      return (
        <FieldRow label="Units">
          <FieldSelect
            value={opts.unit as string}
            options={UNIT_OPTIONS}
            onChange={(v) => set({ unit: v })}
          />
        </FieldRow>
      );
    }
    if (sel === "stl") {
      return (
        <>
          <FieldRow label="Encoding">
            <Segmented
              value={opts.ascii ? "ascii" : "binary"}
              options={[
                { value: "binary", label: "Binary" },
                { value: "ascii", label: "ASCII" },
              ]}
              onChange={(v) => set({ ascii: v === "ascii" })}
            />
          </FieldRow>
          <FieldRow label="Quality" hint="sets tolerance">
            <QualityPreset formatKey="stl" value={opts.quality as string} onPick={pickQuality} />
          </FieldRow>
        </>
      );
    }
    if (sel === "glb") {
      return (
        <>
          <FieldRow label="Container">
            <Segmented
              value={container}
              options={[
                { value: "glb", label: ".glb binary" },
                { value: "gltf", label: ".gltf text" },
              ]}
              onChange={(v) => setContainer(v as "glb" | "gltf")}
            />
          </FieldRow>
          <FieldRow label="Quality" hint="deflection">
            <QualityPreset formatKey="glb" value={opts.quality as string} onPick={pickQuality} />
          </FieldRow>
        </>
      );
    }
    return (
      <>
        <FieldRow label="Units">
          <FieldSelect
            value={opts.unit as string}
            options={UNIT_OPTIONS}
            onChange={(v) => set({ unit: v })}
          />
        </FieldRow>
        <FieldRow label="Quality" hint="mesh deflection">
          <QualityPreset formatKey="3mf" value={opts.quality as string} onPick={pickQuality} />
        </FieldRow>
      </>
    );
  }

  function renderAdvanced() {
    return (
      <div className="overflow-hidden rounded-[11px] border border-line bg-surface-2">
        <button
          type="button"
          onClick={() => setAdvancedOpen((o) => !o)}
          className="flex w-full items-center gap-2.25 px-3.25 py-2.75 text-caption font-semibold text-ink-2"
        >
          <Settings2 size={14} strokeWidth={1.8} /> Advanced options
          <ChevronDown
            size={16}
            strokeWidth={2}
            className={`ml-auto text-ink-3 transition-transform duration-200 ${
              advancedOpen ? "rotate-180" : ""
            }`}
          />
        </button>
        {advancedOpen ? (
          <div className="flex flex-col gap-3.75 border-t border-line px-3.5 pb-4 pt-2.5">
            {renderAdvancedFields()}
          </div>
        ) : null}
      </div>
    );
  }

  function renderAdvancedFields() {
    if (sel === "step") {
      return (
        <>
          <FieldRow label="Precision mode">
            <FieldSelect
              value={opts.precision_mode as string}
              options={PRECISION_OPTIONS}
              onChange={(v) => set({ precision_mode: v })}
            />
          </FieldRow>
          <div className="flex items-center justify-between gap-3.5">
            <div>
              <div className="text-caption font-semibold text-ink-2">Write parametric curves</div>
              <div className="text-micro text-ink-3">Better fidelity, larger files.</div>
            </div>
            <Toggle
              on={opts.write_pcurves as boolean}
              onChange={(v) => set({ write_pcurves: v })}
            />
          </div>
          <FieldRow label="Header timestamp" hint="reproducible builds">
            <Segmented
              value={opts.timestamp === "current" ? "current" : "fixed"}
              options={[
                { value: "current", label: "Current time" },
                { value: "fixed", label: "Fixed" },
              ]}
              onChange={(v) =>
                set({ timestamp: v === "current" ? "current" : "2020-01-01T00:00:00" })
              }
            />
          </FieldRow>
        </>
      );
    }
    if (sel === "stl") {
      return (
        <div className="grid grid-cols-2 gap-4">
          <FieldRow label="Linear tol." hint="mm">
            <NumberField
              value={opts.tolerance as number}
              onChange={(v) => set({ tolerance: v, quality: "custom" })}
            />
          </FieldRow>
          <FieldRow label="Angular tol." hint="rad">
            <NumberField
              value={opts.angular_tolerance as number}
              onChange={(v) => set({ angular_tolerance: v })}
            />
          </FieldRow>
        </div>
      );
    }
    if (sel === "glb") {
      return (
        <>
          <FieldRow label="Units">
            <FieldSelect
              value={opts.unit as string}
              options={UNIT_OPTIONS}
              onChange={(v) => set({ unit: v })}
            />
          </FieldRow>
          <div className="grid grid-cols-2 gap-4">
            <FieldRow label="Linear deflection">
              <NumberField
                value={opts.linear_deflection as number}
                onChange={(v) => set({ linear_deflection: v, quality: "custom" })}
              />
            </FieldRow>
            <FieldRow label="Angular deflection">
              <NumberField
                value={opts.angular_deflection as number}
                onChange={(v) => set({ angular_deflection: v })}
              />
            </FieldRow>
          </div>
        </>
      );
    }
    return (
      <>
        <FieldRow label="Mesh type" hint="print role">
          <FieldSelect
            value={opts.mesh_type as string}
            options={MESH_TYPE_OPTIONS}
            onChange={(v) => set({ mesh_type: v })}
          />
        </FieldRow>
        <div className="grid grid-cols-2 gap-4">
          <FieldRow label="Part number">
            <TextField
              value={opts.part_number as string}
              placeholder="optional"
              onChange={(v) => set({ part_number: v })}
            />
          </FieldRow>
          <FieldRow label="UUID">
            <TextField
              value={opts.uuid as string}
              placeholder="auto"
              onChange={(v) => set({ uuid: v })}
            />
          </FieldRow>
        </div>
      </>
    );
  }
}
