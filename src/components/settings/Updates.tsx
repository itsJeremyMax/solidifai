/**
 * Updates — the "App / Updates" settings section. Bound to the global app-config
 * store plus the shared updater:
 *   • Status row      — up to date / update available, with when it was last
 *     checked and a manual "Check now".
 *   • Update behavior — how an available update is applied (notify / auto-download
 *     / install silently).
 *   • Release channel — Stable or Beta (Beta ships pre-release builds).
 *   • Automatic checks — whether the app checks on launch, on a timer, and on focus.
 *
 * Flags write through `setFlag` (optimistic + persisted). The manual check uses
 * the shared {@link useUpdater} hook so it shares state with the top-bar indicator.
 */
import { useState } from "react";
import { ArrowDownToLine, Check, Loader2, RotateCw, TriangleAlert } from "lucide-react";

import { useAppConfig } from "../../state/appConfig";
import { useUpdater } from "../../state/updater";
import ReleaseNotes from "../update/ReleaseNotes";
import type { UpdateStatus } from "../../hooks/useUpdater";
import type { UpdateBehavior, UpdateChannel } from "../../lib/ipc";

/** Update-behavior choices, in the order they read top-to-bottom. */
const BEHAVIORS: { value: UpdateBehavior; label: string; desc: string }[] = [
  {
    value: "notify",
    label: "Notify me",
    desc: "Show an update badge and let me start the download when I'm ready.",
  },
  {
    value: "autoDownload",
    label: "Download automatically",
    desc: "Fetch and install updates as soon as they're found, then offer a restart.",
  },
  {
    value: "silent",
    label: "Install silently",
    desc: "Install in the background and apply on the next launch, no interruptions.",
  },
];

const CHANNELS: { value: UpdateChannel; label: string }[] = [
  { value: "stable", label: "Stable" },
  { value: "beta", label: "Beta" },
];

/** A plain-language "when" for the last check, e.g. "just now", "5 min ago". */
function relativeTime(from: number, now: number): string {
  const s = Math.max(0, Math.round((now - from) / 1000));
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hr ago`;
  const d = Math.round(h / 24);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

export default function Updates() {
  const { config, setFlag, error } = useAppConfig();
  const { checkNow, lastCheckedAt, status, version, notes, progress, startDownload, restart } =
    useUpdater();

  const [checking, setChecking] = useState(false);
  const [failed, setFailed] = useState(false);

  const handleCheck = async () => {
    setChecking(true);
    setFailed(false);
    try {
      const res = await checkNow();
      setFailed(res.error !== null);
    } finally {
      setChecking(false);
    }
  };

  const busy = checking || status === "checking";
  const pct = progress === null ? null : Math.round(progress * 100);
  const checkedLabel =
    lastCheckedAt !== null
      ? `Checked ${relativeTime(lastCheckedAt, Date.now())}`
      : "Not checked yet";

  // The row's primary action follows the live lifecycle: it only says "Check now"
  // when there's nothing to install; otherwise it becomes the install/restart
  // action. (The "downloading" state renders its own progress row, no button.)
  const action = ((): { label: string; onClick: () => void; tone: ButtonTone; busy?: boolean } => {
    switch (status) {
      case "available":
        return { label: "Install update", onClick: startDownload, tone: "accent" };
      case "ready":
        return { label: "Restart now", onClick: restart, tone: "engine" };
      case "error":
        return { label: "Try again", onClick: startDownload, tone: "accent" };
      default:
        return { label: "Check now", onClick: () => void handleCheck(), tone: "neutral", busy };
    }
  })();

  return (
    <div className="mx-auto max-w-160 py-6.5">
      <h2 className="text-base font-bold tracking-snug text-ink">Updates</h2>
      <p className="mt-1.25 text-body leading-normal text-ink-2">
        How solidifai keeps itself current. It checks on launch, every few hours, and when you
        return to the app.
      </p>

      {error && (
        <div className="mt-3 rounded-lg border border-danger-line bg-danger-bg px-3 py-2 font-mono text-caption text-danger">
          {error}
        </div>
      )}

      {/* Status row: live update state + when last checked + the primary action.
          During a download it becomes a single progress row that moves through
          Downloading -> Installing, so the percentage never appears twice (once in
          a label and again in the button). */}
      <div className="mt-4 rounded-panel border border-line bg-surface px-4 py-3.5">
        {status === "downloading" ? (
          <DownloadingRow pct={pct} />
        ) : (
          <div className="flex items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <StatusBadge status={status} busy={busy} failed={failed} />
              <div className="min-w-0">
                <div className="text-body font-semibold text-ink">
                  <StatusTitle
                    status={status}
                    version={version}
                    pct={pct}
                    busy={busy}
                    failed={failed}
                  />
                </div>
                <div className="mt-0.5 text-caption text-ink-3">{checkedLabel}</div>
              </div>
            </div>
            <ActionButton
              label={action.label}
              onClick={action.onClick}
              tone={action.tone}
              busy={action.busy}
            />
          </div>
        )}
      </div>

      {/* What's new: only while an update is pending, so a user can see what the
          new version brings before installing. */}
      {(status === "available" || status === "ready") && notes && (
        <div className="mt-5.5">
          <h3 className="text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
            What's new{version ? ` in v${version}` : ""}
          </h3>
          <div className="mt-2 rounded-panel border border-line bg-surface px-4 py-3.5">
            <ReleaseNotes notes={notes} className="max-h-64 overflow-y-auto pr-1" />
          </div>
        </div>
      )}

      {/* Update behavior — a radio-style list matching the toggle rows. */}
      <h3 className="mt-5.5 text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
        When an update is available
      </h3>
      <div className="mt-2 divide-y divide-line overflow-hidden rounded-panel border border-line bg-surface">
        {BEHAVIORS.map((b) => {
          const active = config.updateBehavior === b.value;
          return (
            <label
              key={b.value}
              className="flex cursor-pointer items-start gap-3.5 px-4 py-3.5 transition-colors duration-150 hover:bg-surface-2"
            >
              <input
                type="radio"
                name="update-behavior"
                checked={active}
                onChange={() => setFlag("updateBehavior", b.value)}
                className="sr-only"
              />
              <span
                aria-hidden
                className={`mt-0.5 grid h-4.5 w-4.5 shrink-0 place-items-center rounded-full border transition-colors duration-150 ${
                  active ? "border-accent bg-accent" : "border-line-3 bg-surface"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full bg-surface transition-opacity duration-150 ${
                    active ? "opacity-100" : "opacity-0"
                  }`}
                />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-body font-medium text-ink">{b.label}</span>
                <span className="mt-0.5 block text-xs leading-normal text-ink-3">{b.desc}</span>
              </span>
            </label>
          );
        })}
      </div>

      {/* Release channel — a small segmented control. */}
      <h3 className="mt-5.5 text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
        Release channel
      </h3>
      <div className="mt-2 flex items-center justify-between rounded-panel border border-line bg-surface px-4 py-3.5">
        <div className="min-w-0 pr-4">
          <div className="text-body font-medium text-ink">Channel</div>
          <div className="mt-0.5 text-xs leading-normal text-ink-3">
            Beta ships pre-release builds that may be unstable.
          </div>
        </div>
        <div className="inline-flex shrink-0 rounded-lg border border-line-2 bg-surface-2 p-0.75">
          {CHANNELS.map((c) => {
            const active = config.updateChannel === c.value;
            return (
              <button
                key={c.value}
                type="button"
                onClick={() => setFlag("updateChannel", c.value)}
                className={`h-7 rounded-md px-3 text-body font-medium transition-colors duration-150 ${
                  active
                    ? "bg-surface text-ink shadow-[0_1px_2px_rgba(16,18,24,.1)]"
                    : "text-ink-3 hover:text-ink-2"
                }`}
              >
                {c.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Automatic checks toggle. */}
      <h3 className="mt-5.5 text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
        Automatic checks
      </h3>
      <label className="mt-2 flex cursor-pointer items-center justify-between gap-4 rounded-panel border border-line bg-surface px-4 py-3.5 transition-colors duration-150 hover:bg-surface-2">
        <div className="min-w-0 pr-4">
          <div className="text-body font-medium text-ink">Check in the background</div>
          <div className="mt-0.5 text-xs leading-normal text-ink-3">
            On launch, every few hours, and when you return to the app. The manual check always
            works.
          </div>
        </div>
        <input
          type="checkbox"
          checked={config.backgroundUpdateChecks}
          onChange={(e) => setFlag("backgroundUpdateChecks", e.target.checked)}
          className="sr-only"
        />
        <span
          aria-hidden
          className={`relative h-5.5 w-9.5 shrink-0 rounded-full transition-colors duration-150 ${
            config.backgroundUpdateChecks ? "bg-accent" : "bg-line-3"
          }`}
        >
          <span
            className={`absolute top-0.5 h-4.5 w-4.5 rounded-full bg-surface shadow-[0_1px_2px_rgba(16,18,24,.2)] transition-[left] duration-150 ${
              config.backgroundUpdateChecks ? "left-4.5" : "left-0.5"
            }`}
          />
        </span>
      </label>
    </div>
  );
}

function StatusBadge({
  status,
  busy,
  failed,
}: {
  status: UpdateStatus;
  busy: boolean;
  failed: boolean;
}) {
  const box = "grid h-8 w-8 shrink-0 place-items-center rounded-lg";
  if (busy || status === "downloading") {
    return (
      <span className={`${box} bg-surface-2 text-ink-3`}>
        <Loader2 className="animate-spin" size={16} strokeWidth={2.2} />
      </span>
    );
  }
  if (status === "available") {
    return (
      <span className={`${box} bg-accent-bg text-accent`}>
        <ArrowDownToLine size={16} strokeWidth={2} />
      </span>
    );
  }
  if (status === "ready") {
    return (
      <span className={`${box} bg-engine/12 text-engine`}>
        <RotateCw size={16} strokeWidth={2} />
      </span>
    );
  }
  if (status === "error" || failed) {
    return (
      <span className={`${box} bg-danger-bg text-danger`}>
        <TriangleAlert size={16} strokeWidth={2} />
      </span>
    );
  }
  return (
    <span className={`${box} bg-engine/12 text-engine`}>
      <Check size={17} strokeWidth={2.2} />
    </span>
  );
}

function StatusTitle({
  status,
  version,
  pct,
  busy,
  failed,
}: {
  status: UpdateStatus;
  version: string | null;
  pct: number | null;
  busy: boolean;
  failed: boolean;
}) {
  if (busy) return <>Checking for updates</>;
  switch (status) {
    case "available":
      return <>Update available{version ? `: v${version}` : ""}</>;
    case "downloading":
      return <>{pct === null ? "Downloading" : `Downloading ${pct}%`}</>;
    case "ready":
      return <>Update ready to install</>;
    case "error":
      return <>Update failed</>;
    default:
      return failed ? <>Couldn't check for updates</> : <>You're up to date</>;
  }
}

/** The single download/install progress row shown while an update is installing. */
function DownloadingRow({ pct }: { pct: number | null }) {
  // The download reports 0..100%; the brief install phase afterwards has no byte
  // progress, so at 100% (or unknown total) we switch to an indeterminate
  // "Installing" bar. One indicator, two phases.
  const installing = pct === null || pct >= 100;
  return (
    <div className="flex items-center gap-3">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-surface-2 text-ink-3">
        <Loader2 className="animate-spin" size={16} strokeWidth={2.2} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between">
          <span className="text-body font-semibold text-ink">
            {installing ? "Installing…" : "Downloading"}
          </span>
          {!installing && (
            <span className="font-mono text-caption font-semibold tabular-nums text-accent">
              {pct}%
            </span>
          )}
        </div>
        <div className="relative mt-2 h-1.75 overflow-hidden rounded-full bg-line-2">
          {installing ? (
            <span className="absolute inset-y-0 left-0 w-full animate-pulse rounded-full bg-accent" />
          ) : (
            <span
              className="absolute inset-y-0 left-0 rounded-full bg-accent transition-[width] duration-200 ease-out-soft"
              style={{ width: `${Math.max(4, pct ?? 0)}%` }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

type ButtonTone = "accent" | "engine" | "neutral";

function ActionButton({
  label,
  onClick,
  tone,
  busy,
}: {
  label: string;
  onClick: () => void;
  tone: ButtonTone;
  busy?: boolean;
}) {
  const tones: Record<ButtonTone, string> = {
    accent: "bg-accent text-white hover:bg-accent-press",
    engine: "bg-engine text-white hover:opacity-90",
    neutral:
      "border border-line-2 bg-surface text-ink-2 hover:border-line-3 hover:text-ink disabled:hover:border-line-2 disabled:hover:text-ink-2",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!!busy}
      className={`inline-flex h-8 shrink-0 items-center gap-1.75 rounded-lg px-3 text-body font-medium transition-colors duration-150 disabled:opacity-50 ${tones[tone]}`}
    >
      {busy && <Loader2 className="animate-spin" size={14} strokeWidth={2.2} />}
      {label}
    </button>
  );
}
