/**
 * Field primitives for the ExportDialog. Plain, controlled inputs in the app
 * design language (cobalt accent, soft surfaces, dense type scale). No copy here
 * uses em dashes.
 */
import { ChevronDown } from "lucide-react";

export function FieldRow({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.75">
      <span className="text-caption font-semibold text-ink-2">
        {label}
        {hint ? <span className="ml-1.5 font-normal text-ink-3">{hint}</span> : null}
      </span>
      {children}
    </label>
  );
}

export function Segmented({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="inline-flex gap-0.5 rounded-lg border border-line-2 bg-surface-2 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-2.75 py-1.25 text-caption transition-colors duration-150 ${
            value === o.value
              ? "bg-surface font-semibold text-ink shadow-[0_1px_2px_rgba(16,18,24,.1)]"
              : "font-medium text-ink-2 hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function FieldSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8.5 w-full appearance-none rounded-lg border border-line-2 bg-surface pl-2.75 pr-7.5 text-body text-ink transition-colors duration-150 hover:border-line-3 focus:border-accent-line focus:outline-none"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown
        size={14}
        strokeWidth={2}
        className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-3"
      />
    </div>
  );
}

export function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={`relative h-5.5 w-9.5 flex-none rounded-full border transition-colors duration-150 ${
        on ? "border-transparent bg-accent" : "border-line-2 bg-surface-2"
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-[0_1px_2px_rgba(16,18,24,.25)] transition-transform duration-150 ${
          on ? "translate-x-4" : ""
        }`}
      />
    </button>
  );
}

export function NumberField({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <input
      type="number"
      value={value}
      step="any"
      onChange={(e) => onChange(Number(e.target.value))}
      className="h-8.5 w-full rounded-lg border border-line-2 bg-surface px-2.75 font-mono text-caption text-ink focus:border-accent-line focus:outline-none"
    />
  );
}

export function TextField({
  value,
  placeholder,
  onChange,
}: {
  value: string;
  placeholder?: string;
  onChange: (v: string) => void;
}) {
  return (
    <input
      type="text"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className="h-8.5 w-full rounded-lg border border-line-2 bg-surface px-2.75 font-mono text-caption text-ink placeholder:font-ui placeholder:text-ink-3 focus:border-accent-line focus:outline-none"
    />
  );
}

export function QualityPreset({
  formatKey,
  value,
  onPick,
}: {
  formatKey: string;
  value: string;
  onPick: (q: "draft" | "standard" | "fine") => void;
}) {
  const presets: { q: "draft" | "standard" | "fine"; mm: number }[] =
    formatKey === "stl"
      ? [
          { q: "draft", mm: 0.05 },
          { q: "standard", mm: 0.01 },
          { q: "fine", mm: 0.001 },
        ]
      : [
          { q: "draft", mm: 0.01 },
          { q: "standard", mm: 0.001 },
          { q: "fine", mm: 0.0005 },
        ];
  return (
    <div className="grid grid-cols-3 gap-2">
      {presets.map((p) => (
        <button
          key={p.q}
          type="button"
          aria-pressed={value === p.q}
          onClick={() => onPick(p.q)}
          className={`rounded-[10px] border px-3 py-2.75 text-left transition-colors duration-150 ${
            value === p.q
              ? "border-accent-line bg-accent-tint shadow-[0_0_0_3px_var(--color-accent-tint)]"
              : "border-line-2 bg-surface hover:border-line-3"
          }`}
        >
          <div className="text-body font-semibold capitalize text-ink">{p.q}</div>
          <div className="mt-0.5 font-mono text-micro text-ink-3">{p.mm} mm</div>
        </button>
      ))}
    </div>
  );
}
