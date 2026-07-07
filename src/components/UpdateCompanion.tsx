/**
 * UpdateCompanion — the proactive startup card. When an update is first surfaced
 * (or an install finishes / fails), a card rises from the bottom-right carrying
 * the same {@link UpdateCard} content the header pill's popover shows.
 *
 * It is a transient announcement, not a second persistent surface: an
 * available/ready card lingers briefly, then folds into the header pill (the
 * provider marks it dismissed). Downloading and error states stay until they
 * resolve or the user dismisses them. It is fully suppressed on the Settings →
 * Updates page, where that page is the single update surface, and stays quiet for
 * silent installs and the internal "checking" state.
 */
import { useEffect, useState } from "react";

import { useUpdater } from "../state/updater";
import { useOnUpdatesPage } from "../hooks/useOnUpdatesPage";
import UpdateCard from "./update/UpdateCard";

/** How long an announcement lingers before it folds into the header pill. */
const AUTO_FOLD_MS = 9000;
/** Exit-transition duration; keep mounted this long so the fold animates out. */
const EXIT_MS = 300;

export default function UpdateCompanion() {
  const { status, dismissed, dismiss } = useUpdater();
  const onUpdatesPage = useOnUpdatesPage();

  const shouldShow =
    !dismissed &&
    !onUpdatesPage &&
    (status === "available" ||
      status === "downloading" ||
      status === "ready" ||
      status === "error");

  // Announce-then-fold: an available/ready card tucks into the pill after a beat.
  // Downloading/error stay put until they resolve or are dismissed.
  useEffect(() => {
    if (!shouldShow) return;
    if (status !== "available" && status !== "ready") return;
    const t = window.setTimeout(dismiss, AUTO_FOLD_MS);
    return () => window.clearTimeout(t);
  }, [shouldShow, status, dismiss]);

  // Mount with an enter transition; keep mounted briefly on the way out so the
  // fold animates instead of popping.
  const [render, setRender] = useState(false);
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    if (shouldShow) {
      setRender(true);
      const raf = requestAnimationFrame(() => setEntered(true));
      return () => cancelAnimationFrame(raf);
    }
    setEntered(false);
    const t = window.setTimeout(() => setRender(false), EXIT_MS);
    return () => window.clearTimeout(t);
  }, [shouldShow]);

  if (!render) return null;

  return (
    <div
      className={`fixed bottom-4 right-4 z-40 transition duration-300 ease-out-soft motion-reduce:transition-none ${
        entered ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"
      }`}
    >
      <UpdateCard />
    </div>
  );
}
