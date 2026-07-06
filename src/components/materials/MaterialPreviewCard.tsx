/**
 * MaterialPreviewCard — the floating live preview that sits to the LEFT of the
 * editor drawer.
 *
 * This card floats just outside the drawer's
 * left edge, vertically aligned with the drawer header, and tracks the live
 * `draft` the editor is editing. It re-renders as base / color / finish change
 * via `useShadeBall`, and while that WebGPU thumbnail is in flight it paints the
 * same tinted CSS sphere `MaterialCard` uses, so it never flashes empty.
 *
 * Explicit fixed dimensions (a 216px square stage) mean it can never collapse
 * like the old in-form bar did. The surface uses the shared float tokens
 * (`shadow-float`, `rounded-panel`, `border-line-2`, `bg-surface`) and a subtle
 * `animate-rise` entrance.
 *
 * All visible copy comes from MAT_COPY (no em dashes, hand-written voice).
 */
import type { Material } from "../../lib/materials";
import { useShadeBall } from "../../hooks/useShadeBall";
import { MAT_COPY } from "./copy";

/** Title-case a single word ("matte" -> "Matte"). */
function cap(s: string): string {
  return s.length ? s[0].toUpperCase() + s.slice(1) : s;
}

interface MaterialPreviewCardProps {
  /** The live-edited draft the editor drawer is currently showing. */
  material: Material;
}

export default function MaterialPreviewCard({ material }: MaterialPreviewCardProps) {
  const thumb = useShadeBall(material);

  // Color is only trustworthy as a #rrggbb hex; an in-progress value falls back
  // to the neutral grey so the sphere never tints to garbage mid-type.
  const hexValid = /^#[0-9a-fA-F]{6}$/.test(material.colorHex);
  const albedo = hexValid ? material.colorHex : "#bcbfc4";

  // Caption: name (or a gentle placeholder) over "BASE · Finish".
  const name = material.label.trim() || MAT_COPY.previewUntitled;
  const meta = `${material.base.toUpperCase()} · ${cap(material.finish)}`;

  return (
    <div className="animate-rise w-54 overflow-hidden rounded-panel border border-line-2 bg-surface shadow-float">
      {/* live stage: soft radial sweep + contact-shadow floor */}
      <div className="relative grid h-54 place-items-center overflow-hidden border-b border-line-2 bg-[radial-gradient(130%_100%_at_50%_16%,#fcfcfb,#edece8_72%,#e6e4df)]">
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-2/5 bg-[linear-gradient(180deg,transparent,rgba(20,24,36,.05))]" />
        <span className="absolute right-2.75 top-2.5 inline-flex items-center gap-1.5 font-mono text-micro text-ink-3">
          <i className="h-1.5 w-1.5 rounded-full bg-engine shadow-[0_0_0_3px_rgba(25,169,87,.15)]" />
          {MAT_COPY.previewLive}
        </span>
        {thumb ? (
          <img src={thumb} alt="" draggable={false} className="h-30 w-30 select-none" />
        ) : (
          <span
            aria-hidden
            className="relative h-30 w-30 rounded-full shadow-[inset_0_-8px_16px_rgba(8,10,18,.3),inset_0_5px_11px_rgba(255,255,255,.14),0_6px_14px_-6px_rgba(16,18,24,.26)]"
            style={{
              ["--albedo" as string]: albedo,
              background:
                "radial-gradient(circle at 35% 29%, color-mix(in srgb, var(--albedo), white 78%) 0%, transparent 44%)," +
                "radial-gradient(circle at 66% 76%, rgba(150,175,255,.4) 0%, transparent 40%)," +
                "radial-gradient(125% 125% at 47% 35%, color-mix(in srgb, var(--albedo), white 14%), color-mix(in srgb, var(--albedo), black 40%) 84%)",
            }}
          />
        )}
      </div>

      {/* caption: name + base · finish, matching the grid cards' type styles */}
      <div className="flex flex-col items-center gap-1 px-3 pb-3.25 pt-2.75">
        <div className="max-w-full truncate text-body font-semibold tracking-[-0.005em] text-ink">
          {name}
        </div>
        <div className="font-mono text-micro tracking-[0.01em] text-ink-3">{meta}</div>
      </div>
    </div>
  );
}
