/**
 * MaterialCard — one shade-ball card in the materials grid.
 *
 * The shade ball comes from `useShadeBall(material)` (a cached offscreen WebGPU
 * thumbnail). While that render is in flight it returns null, so the card paints
 * a CSS radial-gradient sphere tinted with the material's color in the meantime
 * (the same fake-PBR sphere the mockup uses), and never flashes empty.
 *
 * The card is a real `<button>` for keyboard + screen-reader access; `selected`
 * is surfaced as `aria-pressed`. Badges (Default / Pinned / Local / global) are
 * pinned to the corners.
 */
import { Globe } from "lucide-react";
import type { Material } from "../../lib/materials";
import { useShadeBall } from "../../hooks/useShadeBall";

/** Workspace-scope provenance of a card (drives the corner badge). */
export type CardOrigin = "pinned" | "local" | "global";

interface MaterialCardProps {
  material: Material;
  isDefault: boolean;
  /** Workspace scope only: how this material reaches the workspace. */
  origin?: CardOrigin;
  selected?: boolean;
  onClick: () => void;
}

/** Title-case a single word ("matte" -> "Matte"). */
function cap(s: string): string {
  return s.length ? s[0].toUpperCase() + s.slice(1) : s;
}

export default function MaterialCard({
  material,
  isDefault,
  origin,
  selected = false,
  onClick,
}: MaterialCardProps) {
  const thumb = useShadeBall(material);

  const meta = `${material.base.toUpperCase()} · ${cap(material.finish)}`;

  // The pinned/default badge wins the top-left slot; the read-only "global" tag
  // (workspace scope) sits top-right and stays ghosted.
  const showGlobalTag = origin === "global";

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      title={material.label}
      className={`group relative flex cursor-pointer flex-col items-center gap-3.25 rounded-[15px] border bg-surface px-4 pb-3.75 pt-5 shadow-[0_1px_2px_rgba(16,18,24,.04)] transition duration-200 ease-out-soft hover:-translate-y-0.5 hover:border-line-3 hover:shadow-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-tint ${
        selected
          ? "border-accent-line shadow-[0_0_0_3px_var(--color-accent-tint),0_14px_30px_-14px_rgba(16,18,24,.18)]"
          : "border-line-2"
      }`}
    >
      {isDefault && origin == null && (
        <span className="absolute left-2.5 top-2.5 rounded-full bg-accent px-2 py-[3px] text-micro font-bold leading-none tracking-[0.02em] text-white shadow-[0_1px_2px_rgba(27,73,201,.35)]">
          Default
        </span>
      )}
      {origin === "pinned" && (
        <span className="absolute left-2.5 top-2.5 rounded-full border border-accent-line bg-accent-tint px-2 py-[3px] text-micro font-bold leading-none tracking-[0.02em] text-accent">
          {isDefault ? "Pinned · Default" : "Pinned"}
        </span>
      )}
      {origin === "local" && (
        <span className="absolute left-2.5 top-2.5 rounded-full border border-[rgba(25,169,87,.3)] bg-[rgba(25,169,87,.1)] px-2 py-[3px] text-micro font-bold leading-none tracking-[0.02em] text-engine">
          {isDefault ? "Local · Default" : "Local"}
        </span>
      )}
      {showGlobalTag && (
        <span className="absolute right-2.75 top-2.75 inline-flex items-center gap-1 font-mono text-micro text-ink-3 opacity-80">
          <Globe size={11} strokeWidth={2} />
          global
        </span>
      )}

      {/* shade ball — WebGPU thumbnail, or tinted CSS sphere while it renders */}
      {thumb ? (
        <img src={thumb} alt="" draggable={false} className="h-20.5 w-20.5 select-none" />
      ) : (
        <ShadeBallFallback colorHex={material.colorHex} />
      )}

      <div className="text-center text-body font-semibold tracking-[-0.005em] text-ink">
        {material.label}
      </div>
      <div className="-mt-1 flex items-center gap-1.5 font-mono text-micro tracking-[0.01em] text-ink-3">
        {meta}
      </div>
    </button>
  );
}

/**
 * A CSS radial-gradient sphere tinted by the material color, shown until the
 * real thumbnail arrives. Mirrors the mockup's fake-PBR ball so the swap is
 * visually quiet (no empty flash, no layout shift).
 */
function ShadeBallFallback({ colorHex }: { colorHex: string }) {
  return (
    <span
      aria-hidden
      className="relative h-20.5 w-20.5 flex-none rounded-full shadow-[inset_0_-8px_16px_rgba(8,10,18,.3),inset_0_5px_11px_rgba(255,255,255,.14),0_6px_14px_-6px_rgba(16,18,24,.26)]"
      style={{
        ["--albedo" as string]: colorHex,
        background:
          "radial-gradient(circle at 35% 29%, color-mix(in srgb, var(--albedo), white 78%) 0%, transparent 44%)," +
          "radial-gradient(circle at 66% 76%, rgba(150,175,255,.4) 0%, transparent 40%)," +
          "radial-gradient(125% 125% at 47% 35%, color-mix(in srgb, var(--albedo), white 14%), color-mix(in srgb, var(--albedo), black 40%) 84%)",
      }}
    />
  );
}
