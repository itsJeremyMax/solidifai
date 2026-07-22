/**
 * Select — the app's dropdown control. A native <select> with `appearance-none`
 * (no OS chrome) and an overlaid chevron, styled to match the field primitives in
 * the Export dialog so every dropdown reads the same: soft surface, line-2
 * border, cobalt focus, rounded-lg. Use this for any dropdown rather than a bare
 * <select>.
 */
import { ChevronDown } from "lucide-react";

export interface SelectOption {
  value: string;
  label: string;
}

export default function Select({
  value,
  onChange,
  options,
  className = "",
  ariaLabel,
  ariaDescribedBy,
  disabled = false,
}: {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
  /** Wrapper classes — set the width here (defaults to full width). */
  className?: string;
  ariaLabel?: string;
  ariaDescribedBy?: string;
  /** Greys out + blocks the control (e.g. no options to choose beyond a default). */
  disabled?: boolean;
}) {
  return (
    <div className={`relative ${className || "w-full"}`}>
      <select
        value={value}
        aria-label={ariaLabel}
        aria-describedby={ariaDescribedBy}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="h-8.5 w-full cursor-pointer appearance-none rounded-lg border border-line-2 bg-surface pl-2.75 pr-7.5 text-body text-ink transition-colors duration-150 hover:border-line-3 focus:border-accent-line focus:outline-none disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-ink-3 disabled:hover:border-line-2"
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
