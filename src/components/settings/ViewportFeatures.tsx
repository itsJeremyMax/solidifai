/**
 * ViewportFeatures — the "Viewport / Features" settings section. A list of
 * toggles bound to the global app-config store. Each toggle writes
 * through `setFlag` (persisted via `set_app_config`) and the editor scene applies
 * the flag live (see Viewport.tsx). These flags are GLOBAL — they apply to every
 * workspace's Preview.
 */
import { useAppConfig } from "../../state/appConfig";
import type { AppConfig } from "../../lib/ipc";

/** One viewport feature flag row (a boolean key of AppConfig). */
type FlagKey = "gtao" | "grid" | "smaa" | "softShadows";

interface FeatureRow {
  key: FlagKey;
  label: string;
  desc: string;
}

/** The four toggleable Preview features. */
const FEATURES: FeatureRow[] = [
  {
    key: "gtao",
    label: "Ambient occlusion",
    desc: "Screen-space contact shading (GTAO). Adds depth at crevices; weakest at grazing angles.",
  },
  {
    key: "grid",
    label: "Work-plane grid",
    desc: "The studio floor grid the part sits on.",
  },
  {
    key: "smaa",
    label: "Anti-aliasing",
    desc: "Temporal anti-aliasing (TRAA) over the rendered part.",
  },
  {
    key: "softShadows",
    label: "Soft shadows",
    desc: "Blurred contact shadow under the part (vs a crisp hard edge).",
  },
];

/**
 * A small accessible pill toggle — the graphite Apple-meets-Atlassian idiom:
 * accent fill when on, a `line-2` track when off, a soft surface knob that
 * slides with a short eased transition. Used by both settings sections.
 */
function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={onChange}
      className={`group relative inline-flex h-5.5 w-9.5 shrink-0 items-center rounded-full outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent-tint ${
        checked ? "bg-accent" : "bg-line-2 hover:bg-[rgba(18,20,28,.2)]"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-surface shadow-[0_1px_2px_rgba(16,18,24,.28)] transition-transform duration-150 ${
          checked ? "translate-x-4.75" : "translate-x-0.75"
        }`}
      />
    </button>
  );
}

export default function ViewportFeatures() {
  const { config, setFlag, error } = useAppConfig();

  return (
    <div className="mx-auto max-w-160 py-6.5">
      <h2 className="text-base font-bold tracking-snug text-ink">Viewport / Features</h2>
      <p className="mt-1.25 text-body leading-normal text-ink-2">
        Real-time Preview rendering effects. Changes apply live and persist across workspaces.
      </p>

      {error && (
        <div className="mt-3 rounded-lg border border-danger-line bg-danger-bg px-3 py-2 font-mono text-caption text-danger">
          {error}
        </div>
      )}

      <div className="mt-4.5 divide-y divide-line overflow-hidden rounded-panel border border-line bg-surface">
        {FEATURES.map((f) => (
          <label
            key={f.key}
            className="flex cursor-pointer items-start gap-4 px-4 py-3.5 transition-colors duration-150 hover:bg-surface-2"
          >
            <div className="min-w-0 flex-1">
              <div className="text-body font-medium text-ink">{f.label}</div>
              <div className="mt-0.5 text-xs leading-normal text-ink-3">{f.desc}</div>
            </div>
            <Toggle
              checked={config[f.key]}
              label={f.label}
              onChange={() => setFlag(f.key, !config[f.key] as AppConfig[FlagKey])}
            />
          </label>
        ))}
      </div>
    </div>
  );
}
