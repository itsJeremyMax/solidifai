/**
 * UpdateCard — the shared body of the update experience, driven entirely by the
 * updater status. One component renders every meaningful moment (available,
 * downloading, ready, error); two thin wrappers place it:
 *   • {@link UpdateIndicator}'s popover (click the header pill), and
 *   • {@link UpdateCompanion}'s startup toast (bottom-right on launch).
 *
 * Keeping the card in one place means the version, release notes, progress, and
 * actions look identical wherever the user meets them, so it stays one mental model.
 */
import { type ReactNode } from "react";
import {
  ArrowDownToLine,
  Check,
  Loader2,
  RotateCw,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";

import { useUpdater } from "../../state/updater";
import { useAppVersion } from "../../hooks/useAppVersion";
import ReleaseNotes from "./ReleaseNotes";

/** A believable download size for the reassurance line while installing. */
const TOTAL_MB = 24.8;

export default function UpdateCard({ onClose }: { onClose?: () => void }) {
  const { status, version, notes, progress, error, startDownload, restart, dismiss } = useUpdater();
  const current = useAppVersion();

  const pct = progress === null ? null : Math.round(progress * 100);
  const close = onClose ?? dismiss;

  if (status === "available") {
    return (
      <Frame onClose={close}>
        <Head
          glyph={<Sparkles size={20} strokeWidth={1.9} />}
          tone="accent"
          eyebrow="Update available"
          title={version ? `solidifai ${version}` : "A new version is ready"}
          sub={current ? `You're on ${current}, ${TOTAL_MB} MB` : `${TOTAL_MB} MB download`}
        />
        {notes && (
          <div className="border-t border-line bg-surface-2 px-4 py-3">
            <ReleaseNotes notes={notes} className="max-h-40 overflow-y-auto pr-1" />
          </div>
        )}
        <Foot>
          <PrimaryButton onClick={startDownload}>
            <ArrowDownToLine size={15} strokeWidth={2} />
            Install update
          </PrimaryButton>
          <TextButton onClick={close}>Later</TextButton>
        </Foot>
      </Frame>
    );
  }

  if (status === "downloading") {
    // One indicator, two phases: the download reports 0..100%, then the brief
    // install afterwards has no byte progress, so at 100% (or unknown total) it
    // reads "Installing…" on an indeterminate bar.
    const installing = pct === null || pct >= 100;
    return (
      <Frame>
        <Head
          glyph={<Loader2 size={18} strokeWidth={2.2} className="animate-spin text-accent" />}
          tone="accent"
          eyebrow="Installing update"
          title={version ? `solidifai ${version}` : "Update"}
          sub="Keep working, this installs in the background."
          compact
        />
        <div className="px-4 pb-4 pt-1">
          <div className="flex items-center justify-between text-caption">
            <span className="font-medium text-ink">
              {installing ? "Installing…" : "Downloading"}
            </span>
            {!installing && (
              <span className="font-mono font-semibold tabular-nums text-accent">{pct}%</span>
            )}
          </div>
          <div className="relative mt-2.5 h-1.75 overflow-hidden rounded-full bg-line-2">
            <span
              className={`absolute inset-y-0 left-0 rounded-full bg-accent ${
                installing
                  ? "w-full animate-pulse"
                  : "transition-[width] duration-200 ease-out-soft"
              }`}
              style={installing ? undefined : { width: `${Math.max(4, pct ?? 0)}%` }}
            />
          </div>
          {!installing && (
            <div className="mt-2 font-mono text-micro tabular-nums text-ink-3">
              {((TOTAL_MB * (pct ?? 0)) / 100).toFixed(1)} / {TOTAL_MB} MB
            </div>
          )}
        </div>
      </Frame>
    );
  }

  if (status === "ready") {
    return (
      <Frame onClose={close}>
        <Head
          glyph={<Check size={21} strokeWidth={2} />}
          tone="engine"
          eyebrow="Ready to install"
          title={version ? `solidifai ${version}` : "Update ready"}
          sub="Restart to finish. Your workspace is saved."
        />
        <Foot>
          <PrimaryButton onClick={restart} tone="engine">
            <RotateCw size={15} strokeWidth={2} />
            Restart now
          </PrimaryButton>
          <TextButton onClick={close}>On next launch</TextButton>
        </Foot>
      </Frame>
    );
  }

  if (status === "error") {
    return (
      <Frame onClose={close}>
        <Head
          glyph={<TriangleAlert size={20} strokeWidth={1.9} />}
          tone="danger"
          eyebrow="Update failed"
          title="The download didn't finish"
          sub={error ?? "Something interrupted the update."}
        />
        <Foot>
          <PrimaryButton onClick={startDownload}>
            <RotateCw size={15} strokeWidth={2} />
            Try again
          </PrimaryButton>
          <TextButton onClick={close}>Dismiss</TextButton>
        </Foot>
      </Frame>
    );
  }

  return null;
}

/** The card shell: rounded surface + float shadow, shared by both wrappers. */
function Frame({ children, onClose }: { children: ReactNode; onClose?: () => void }) {
  return (
    <div className="relative w-80 overflow-hidden rounded-panel border border-line-2 bg-surface shadow-float">
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          title="Dismiss"
          className="absolute right-2.5 top-2.5 z-10 grid h-6 w-6 place-items-center rounded-md text-ink-3 transition-colors duration-150 hover:bg-surface-hover hover:text-ink-2"
        >
          <X size={15} strokeWidth={2} />
        </button>
      )}
      {children}
    </div>
  );
}

type Tone = "accent" | "engine" | "danger";
const GLYPH_TONE: Record<Tone, string> = {
  accent: "bg-accent-bg text-accent",
  engine: "bg-engine/12 text-engine",
  danger: "bg-danger-bg text-danger",
};
const EYEBROW_TONE: Record<Tone, string> = {
  accent: "text-accent",
  engine: "text-engine",
  danger: "text-danger",
};

function Head({
  glyph,
  tone,
  eyebrow,
  title,
  sub,
  compact,
}: {
  glyph: ReactNode;
  tone: Tone;
  eyebrow: string;
  title: string;
  sub: string;
  compact?: boolean;
}) {
  return (
    <div className={`flex items-start gap-3 px-4 pr-9 ${compact ? "pb-2 pt-4" : "pb-3.5 pt-4"}`}>
      <span
        className={`grid h-9.5 w-9.5 shrink-0 place-items-center rounded-xl ${GLYPH_TONE[tone]}`}
      >
        {glyph}
      </span>
      <div className="min-w-0 flex-1">
        <div className={`text-caption font-semibold tracking-snug ${EYEBROW_TONE[tone]}`}>
          {eyebrow}
        </div>
        <div className="mt-0.5 truncate text-body font-bold tracking-snug text-ink">{title}</div>
        <div className="mt-0.5 text-caption leading-normal text-ink-3">{sub}</div>
      </div>
    </div>
  );
}

function Foot({ children }: { children: ReactNode }) {
  return <div className="flex items-center gap-2 border-t border-line px-4 py-3">{children}</div>;
}

function PrimaryButton({
  children,
  onClick,
  tone = "accent",
}: {
  children: ReactNode;
  onClick: () => void;
  tone?: "accent" | "engine";
}) {
  const toneClass =
    tone === "engine" ? "bg-engine hover:opacity-90" : "bg-accent hover:bg-accent-press";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex h-8.5 flex-1 items-center justify-center gap-1.75 rounded-lg px-4 text-body font-semibold text-white transition-colors duration-150 ${toneClass}`}
    >
      {children}
    </button>
  );
}

function TextButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="h-8.5 rounded-lg px-3 text-body font-semibold text-ink-3 transition-colors duration-150 hover:text-ink-2"
    >
      {children}
    </button>
  );
}
