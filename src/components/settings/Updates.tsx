/**
 * Updates — the "App / Updates" settings section. Three controls bound to the
 * global app-config store:
 *   • Update behavior — how an available update is applied (notify / auto-download
 *     / install silently).
 *   • Release channel — Stable or Beta (Beta ships pre-release builds).
 *   • Check for updates — a manual re-check that surfaces the result inline.
 *
 * Behavior + channel write through `setFlag` (optimistic + persisted, like
 * ViewportFeatures). The manual check uses the shared {@link useUpdater} hook so
 * it shares state with the top-bar indicator.
 */
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { useAppConfig } from "../../state/appConfig";
import { useUpdater } from "../../state/updater";
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

/** The result of a manual check, shown inline under the button. */
type CheckResult =
  | { kind: "uptodate" }
  | { kind: "available"; version: string | null }
  | { kind: "failed"; message: string };

export default function Updates() {
  const { config, setFlag, error } = useAppConfig();
  const { checkNow } = useUpdater();

  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<CheckResult | null>(null);

  const handleCheck = async () => {
    setChecking(true);
    setResult(null);
    try {
      const res = await checkNow();
      setResult(
        res.error !== null
          ? { kind: "failed", message: res.error }
          : res.available
            ? { kind: "available", version: res.version }
            : { kind: "uptodate" },
      );
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="mx-auto max-w-160 py-6.5">
      <h2 className="text-base font-bold tracking-snug text-ink">Updates</h2>
      <p className="mt-1.25 text-body leading-normal text-ink-2">
        How solidifai keeps itself current. The app checks for a new version on launch.
      </p>

      {error && (
        <div className="mt-3 rounded-lg border border-danger-line bg-danger-bg px-3 py-2 font-mono text-caption text-danger">
          {error}
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

      {/* Manual check. */}
      <div className="mt-5.5 flex items-center gap-3">
        <button
          type="button"
          onClick={() => void handleCheck()}
          disabled={checking}
          className="inline-flex h-8 items-center gap-1.75 rounded-lg border border-line-2 bg-surface px-3 text-body font-medium text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink disabled:opacity-50 disabled:hover:border-line-2 disabled:hover:text-ink-2"
        >
          {checking && <Loader2 className="animate-spin" size={14} strokeWidth={2.2} />}
          Check for updates
        </button>
        {result &&
          (result.kind === "failed" ? (
            <span className="text-body text-danger">Couldn't check for updates.</span>
          ) : (
            <span className="text-body text-ink-2">
              {result.kind === "uptodate"
                ? "You are up to date."
                : `Update available: v${result.version ?? "?"}.`}
            </span>
          ))}
      </div>
    </div>
  );
}
