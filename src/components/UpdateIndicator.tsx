/**
 * UpdateIndicator — the unobtrusive top-bar affordance for an available update.
 *
 * Renders nothing while idle. When an update is available it shows a quiet pill
 * ("Update available") that starts the download on click; while downloading it
 * shows a slim determinate progress bar; when the install is ready it offers
 * "Restart to update"; on failure it shows a quiet error pill that retries the
 * download. It consumes {@link useUpdater} directly (no prop drilling) so it can
 * be dropped anywhere in the chrome.
 */
import { ArrowDownToLine, RotateCw, TriangleAlert } from "lucide-react";

import { useUpdater } from "../state/updater";

const ICON_STROKE = 1.8;

export default function UpdateIndicator() {
  const { status, version, progress, startDownload, restart } = useUpdater();

  if (status === "idle") return null;

  const label = version ? `Update available v${version}` : "Update available";

  if (status === "available") {
    return (
      <button
        type="button"
        onClick={startDownload}
        title="Download and install the latest version"
        className="inline-flex h-8 shrink-0 items-center gap-1.75 whitespace-nowrap rounded-lg border border-accent-line bg-accent-tint px-2.75 text-body font-medium text-accent transition-colors duration-150 hover:border-accent"
      >
        <ArrowDownToLine size={15} strokeWidth={ICON_STROKE} />
        {label}
      </button>
    );
  }

  if (status === "downloading") {
    const pct = progress === null ? null : Math.round(progress * 100);
    return (
      <div
        className="inline-flex h-8 shrink-0 select-none items-center gap-2.25 whitespace-nowrap rounded-lg border border-line-2 bg-surface px-2.75 text-body font-medium text-ink-2"
        title="Downloading the update"
      >
        <span>{pct === null ? "Downloading…" : `Downloading ${pct}%`}</span>
        <span className="relative h-1 w-16 overflow-hidden rounded-full bg-line-2">
          <span
            className="absolute inset-y-0 left-0 rounded-full bg-accent transition-[width] duration-200"
            style={{ width: `${progress === null ? 100 : Math.max(4, (progress ?? 0) * 100)}%` }}
          />
        </span>
      </div>
    );
  }

  if (status === "ready") {
    return (
      <button
        type="button"
        onClick={restart}
        title="Restart to finish updating"
        className="inline-flex h-8 shrink-0 items-center gap-1.75 whitespace-nowrap rounded-lg border border-accent-line bg-accent-tint px-2.75 text-body font-medium text-accent transition-colors duration-150 hover:border-accent"
      >
        <RotateCw size={15} strokeWidth={ICON_STROKE} />
        Restart to update
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={startDownload}
      title="The update did not finish. Click to try again."
      className="inline-flex h-8 shrink-0 items-center gap-1.75 whitespace-nowrap rounded-lg border border-danger-line bg-surface px-2.75 text-body font-medium text-danger transition-colors duration-150 hover:bg-danger-bg"
    >
      <TriangleAlert size={15} strokeWidth={ICON_STROKE} />
      Update failed
    </button>
  );
}
