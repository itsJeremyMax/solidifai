/**
 * ViewportContextMenu — the frosted feature menu that appears on right-click in
 * the viewport. PURE PRESENTATIONAL: every datum and every action arrives via
 * props; this component performs no engine calls and touches no three.js.
 *
 * It adopts the viewport's in-canvas frosted-glass idiom (the same glass tint,
 * hairline border, blur, and mono numerics as the tool dock + measure pill) but
 * a touch denser (~rgba(20,23,30,.72)) so it reads as a focused, opaque menu on
 * the dark graphite stage.
 *
 * Three resolved states (mutually exclusive):
 *  1. Parametric  — a declared, non-inferred feature whose driving param has a
 *                   range schema: header + inline ± stepper + action rows.
 *  2. Inferred / non-parametric — auto-detected or driverless feature: header
 *                   (mono name, amber pill + confidence when inferred) + an
 *                   amber "can't tune directly" note + a reduced row set.
 *  3. Empty       — no feature under the cursor: view-level actions only.
 *
 * Positioning: rendered `absolute` at {x, y} inside the viewport, then clamped
 * and flipped against the offset parent so it never spills past an edge — flip
 * left when it would overrun the right edge, up when it would overrun the
 * bottom. Dismissal (click-outside + Escape) reuses {@link useDismiss}; the ±
 * stepper buttons live inside the menu ref, so clicking them repeats without
 * dismissing.
 */
import { useLayoutEffect, useState } from "react";
import {
  Circle,
  Copy,
  Cylinder,
  Grid3x3,
  Maximize2,
  Minus,
  Plus,
  RotateCcw,
  Ruler,
  Scan,
  SlidersHorizontal,
} from "lucide-react";

import type { EngineFeature } from "../lib/ipc/engine";
import { useDismiss } from "../hooks/useDismiss";

/** Driving-parameter schema for the inline ± stepper. */
export interface ParamRange {
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
}

export interface ViewportContextMenuProps {
  /** Anchor position, viewport-relative px (the right-click point). */
  x: number;
  y: number;
  /** Resolved feature, or `null` for the empty-space variant. */
  feature: EngineFeature | null;
  /** Driving param schema (drives the ± stepper), or `null` if none. */
  paramRange: ParamRange | null;
  /** Driving param key (`feature.driven_by[0]`), or `null`. */
  paramName: string | null;
  /** ± stepper; `delta` is `±paramRange.step`. */
  onStep: (delta: number) => void;
  onOpenInspector: () => void;
  onFrame: () => void;
  onShowDimensions: () => void;
  onCopyReference: () => void;
  /** Empty-state: fit camera to model. */
  onFit: () => void;
  /** Empty-state: reset camera to home. */
  onResetView: () => void;
  /** Empty-state: toggle the work-plane grid. */
  onToggleGrid: () => void;
  onDismiss: () => void;
}

/** Fixed menu width (matches the preview); used for edge-flip math. */
const MENU_W = 248;
/** Keep the menu this far from the viewport edges when clamping. */
const EDGE_PAD = 8;

/** Shared glass + hairline shell — denser sibling of the tool dock overlay. */
const GLASS =
  "rounded-xl border border-term-line bg-[rgba(20,23,30,.72)] " +
  "backdrop-blur-lg backdrop-saturate-[1.2] " +
  "shadow-[0_2px_6px_rgba(0,0,0,.36),0_26px_60px_-22px_rgba(0,0,0,.7)]";

/* ──────────────────────────── building blocks ─────────────────────────── */

/** A single clickable action row (icon · label · optional mono hint). */
function Row({
  icon,
  label,
  hint,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  hint?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="group flex w-full items-center gap-2.75 rounded-lg px-2.5 py-2 text-left text-body leading-none text-term-ink transition-colors duration-100 hover:bg-accent-bg hover:text-white"
    >
      <span className="flex-none text-term-ink-dim transition-colors duration-100 group-hover:text-accent">
        {icon}
      </span>
      <span className="flex-1">{label}</span>
      {hint && (
        <span className="max-w-24 truncate font-mono text-micro text-[#6b7280] transition-colors duration-100 group-hover:text-term-ink">
          {hint}
        </span>
      )}
    </button>
  );
}

/** Hairline divider between groups. */
function Sep() {
  return <div className="mx-2 my-1.25 h-px bg-term-line" />;
}

/** Footer hint line (keyboard affordances or empty-state guidance). */
function Foot({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.75 px-2.75 pb-1.25 pt-1.75 text-caption leading-snug text-[#6b7280]">
      {children}
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded-sm border border-b-2 border-term-line px-1.25 py-px font-mono text-micro text-term-ink-dim">
      {children}
    </kbd>
  );
}

/* ──────────────────────────── the component ───────────────────────────── */

export function ViewportContextMenu({
  x,
  y,
  feature,
  paramRange,
  paramName,
  onStep,
  onOpenInspector,
  onFrame,
  onShowDimensions,
  onCopyReference,
  onFit,
  onResetView,
  onToggleGrid,
  onDismiss,
}: ViewportContextMenuProps) {
  // useDismiss is always-on while mounted (the parent controls mount/unmount).
  const ref = useDismiss<HTMLDivElement>(true, onDismiss);

  // Edge-aware placement: start at {x, y}, then flip left/up against the offset
  // parent (the viewport <section>) so the menu never overflows. Measured after
  // layout so we use the real rendered height.
  const [pos, setPos] = useState<{ left: number; top: number }>({ left: x, top: y });
  useLayoutEffect(() => {
    const el = ref.current;
    const parent = el?.offsetParent as HTMLElement | null;
    const pw = parent?.clientWidth ?? window.innerWidth;
    const ph = parent?.clientHeight ?? window.innerHeight;
    const h = el?.offsetHeight ?? 0;

    // Flip horizontally when the menu would overrun the right edge, then clamp.
    // The upper bound is floored at EDGE_PAD so a menu wider/taller than its
    // container can't invert the clamp (a negative upper bound would otherwise
    // win the Math.min and push the menu off-screen) — it pins to the pad.
    const left = x + MENU_W + EDGE_PAD > pw ? x - MENU_W : x;
    const clampedLeft = Math.max(
      EDGE_PAD,
      Math.min(left, Math.max(EDGE_PAD, pw - MENU_W - EDGE_PAD)),
    );

    const top = y + h + EDGE_PAD > ph ? y - h : y;
    const clampedTop = Math.max(EDGE_PAD, Math.min(top, Math.max(EDGE_PAD, ph - h - EDGE_PAD)));

    setPos({ left: clampedLeft, top: clampedTop });
  }, [x, y, ref, feature, paramRange]);

  const isParametric =
    !!feature && !feature.inferred && feature.driven_by.length > 0 && !!paramRange;
  const isInferredOrPlain = !!feature && (feature.inferred || feature.driven_by.length === 0);

  const ariaLabel = feature ? `${feature.name} actions` : "viewport actions";

  return (
    <div
      ref={ref}
      role="menu"
      aria-label={ariaLabel}
      style={{ left: pos.left, top: pos.top, transformOrigin: "top left" }}
      className={`absolute z-50 w-62 origin-top-left overflow-hidden p-1.5 text-term-ink animate-[solidifai-rise_.16s_cubic-bezier(.2,.7,.2,1)_both] ${GLASS}`}
    >
      {/* hairline top sheen — the Apple-glass tell */}
      <span className="pointer-events-none absolute inset-x-0 top-0 h-px bg-[linear-gradient(90deg,transparent,rgba(255,255,255,.18),transparent)]" />

      {/* ── 1. PARAMETRIC ── */}
      {isParametric && feature && paramRange && (
        <>
          <header className="flex items-start gap-2.5 px-2.5 pb-2 pt-2.25">
            <span className="grid h-7.5 w-7.5 flex-none place-items-center rounded-lg border border-accent-line bg-accent-bg text-accent">
              <Circle size={17} strokeWidth={1.7} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold leading-[1.1] tracking-snug text-term-ink-bright">
                {feature.name}
              </div>
              <div className="mt-0.75 text-caption leading-[1.35] text-term-ink-dim">
                {feature.kind && <span>{feature.kind} · </span>}
                <span className="text-term-ink">drives</span>{" "}
                <code className="font-mono text-caption text-accent">{paramName}</code>
              </div>
            </div>
          </header>

          <div
            role="group"
            aria-label={`adjust ${paramName ?? "parameter"}`}
            className="mx-1.5 mb-1 mt-0.5 rounded-lg border border-accent-line bg-[rgba(43,108,255,.08)] px-2.5 py-2.25"
          >
            <div className="mb-2 flex items-center gap-2">
              <span className="flex-1 font-mono text-caption text-accent">{paramName}</span>
              <span className="text-micro text-term-ink-dim">
                {paramRange.min} – {paramRange.max} {paramRange.unit}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <StepBtn
                label="decrease"
                disabled={paramRange.value <= paramRange.min}
                onClick={() => onStep(-paramRange.step)}
              >
                <Minus size={17} strokeWidth={2} />
              </StepBtn>
              <div className="flex-1 text-center font-mono text-base font-medium text-white">
                {formatValue(paramRange.value)}
                <span className="ml-0.75 text-caption text-term-ink-dim">{paramRange.unit}</span>
              </div>
              <StepBtn
                label="increase"
                disabled={paramRange.value >= paramRange.max}
                onClick={() => onStep(+paramRange.step)}
              >
                <Plus size={17} strokeWidth={2} />
              </StepBtn>
            </div>
          </div>

          <Sep />

          <Row
            icon={<SlidersHorizontal size={16} strokeWidth={1.7} />}
            label="Open in Inspector"
            hint="↵"
            onClick={onOpenInspector}
          />
          <Row
            icon={<Maximize2 size={16} strokeWidth={1.7} />}
            label="Frame this feature"
            onClick={onFrame}
          />
          <Row
            icon={<Ruler size={16} strokeWidth={1.7} />}
            label="Show dimensions"
            onClick={onShowDimensions}
          />
          <Row
            icon={<Copy size={16} strokeWidth={1.7} />}
            label="Copy reference"
            hint={feature.name}
            onClick={onCopyReference}
          />

          <Foot>
            <Kbd>esc</Kbd>
            <span>to dismiss · ↑↓ to navigate</span>
          </Foot>
        </>
      )}

      {/* ── 2. INFERRED / NON-PARAMETRIC ── */}
      {!isParametric && isInferredOrPlain && feature && (
        <>
          <header className="flex items-start gap-2.5 px-2.5 pb-2 pt-2.25">
            <span
              className={
                feature.inferred
                  ? "grid h-7.5 w-7.5 flex-none place-items-center rounded-lg border border-[rgba(224,162,59,.4)] bg-[rgba(224,162,59,.14)] text-amber"
                  : "grid h-7.5 w-7.5 flex-none place-items-center rounded-lg border border-accent-line bg-accent-bg text-accent"
              }
            >
              {feature.inferred ? (
                <Cylinder size={17} strokeWidth={1.7} />
              ) : (
                <Circle size={17} strokeWidth={1.7} />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.75 leading-[1.1] tracking-snug">
                {feature.inferred ? (
                  <span className="font-mono text-body font-medium text-term-ink-bright">
                    {feature.name}
                  </span>
                ) : (
                  <span className="text-sm font-semibold text-term-ink-bright">{feature.name}</span>
                )}
                {feature.inferred && (
                  <span className="rounded-full border border-[rgba(224,162,59,.36)] bg-[rgba(224,162,59,.13)] px-1.5 py-0.5 font-mono text-micro font-medium uppercase leading-none tracking-widest text-amber">
                    inferred
                  </span>
                )}
              </div>
              <div className="mt-0.75 text-caption leading-[1.35] text-term-ink-dim">
                {feature.kind ?? "Feature"}
                {feature.inferred && feature.confidence != null && (
                  <span> · confidence {feature.confidence}</span>
                )}
              </div>
            </div>
          </header>

          {feature.inferred && (
            <div className="mx-1.5 mb-1.5 mt-0.5 rounded-lg border border-[rgba(224,162,59,.28)] bg-[rgba(224,162,59,.07)] px-2.75 py-2.25 text-caption leading-[1.45] text-term-ink">
              <span className="font-semibold text-amber">Auto-detected.</span> No driving parameter,
              so it can&apos;t be tuned directly. Name it with{" "}
              <code className="font-mono text-caption text-term-ink-bright">feature()</code> to make
              it adjustable — or describe the change in the terminal.
            </div>
          )}

          <Sep />

          <Row
            icon={<Maximize2 size={16} strokeWidth={1.7} />}
            label="Frame this feature"
            onClick={onFrame}
          />
          <Row
            icon={<Ruler size={16} strokeWidth={1.7} />}
            label="Show dimensions"
            onClick={onShowDimensions}
          />
          <Row
            icon={<Copy size={16} strokeWidth={1.7} />}
            label="Copy reference"
            hint={feature.name}
            onClick={onCopyReference}
          />

          <Foot>
            <Kbd>esc</Kbd>
            <span>to dismiss · ↑↓ to navigate</span>
          </Foot>
        </>
      )}

      {/* ── 3. EMPTY SPACE ── */}
      {!feature && (
        <>
          <Row
            icon={<Scan size={16} strokeWidth={1.7} />}
            label="Fit to model"
            hint="F"
            onClick={onFit}
          />
          <Row
            icon={<RotateCcw size={16} strokeWidth={1.7} />}
            label="Reset view"
            onClick={onResetView}
          />
          <Row
            icon={<Grid3x3 size={16} strokeWidth={1.7} />}
            label="Toggle work-plane grid"
            onClick={onToggleGrid}
          />
          <Sep />
          <Foot>
            <span className="leading-[1.4]">
              Right-click a feature to highlight, measure, or tune it.
            </span>
          </Foot>
        </>
      )}
    </div>
  );
}

/** Square ± button inside the stepper. Disabled at the param's range bounds. */
function StepBtn({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="grid h-7.5 w-7.5 flex-none place-items-center rounded-lg border border-term-line bg-term-line text-term-ink-bright transition-[background-color,transform] duration-100 hover:enabled:border-transparent hover:enabled:bg-accent hover:enabled:text-white active:enabled:scale-[0.94] disabled:cursor-default disabled:text-[#4d535e] disabled:opacity-50"
    >
      {children}
    </button>
  );
}

/**
 * Format a stepper value: trim to at most one decimal, but drop a trailing
 * `.0` only when the step is whole. Keeps "26.0" for 0.x steps and "26" for
 * integer steps, matching the mono numerics in the dock/HUD.
 */
function formatValue(v: number): string {
  const rounded = Math.round(v * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export default ViewportContextMenu;
