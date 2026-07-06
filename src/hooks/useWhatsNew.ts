/**
 * useWhatsNew — gates the post-update "What's new" fullscreen modal.
 *
 * On the first settled app-config load of a session it reads the running version
 * and the persisted `lastSeenVersion`:
 *   • first ever launch (lastSeen === null) → silently record this version, show
 *     nothing (a brand-new install has no "since you last launched" story).
 *   • updated since last launch → open the modal with every CHANGELOG section in
 *     the (lastSeen, current] range, but only if there's actually something to show.
 *   • unchanged → do nothing.
 *
 * Dismissing persists `lastSeenVersion = current` so the modal won't reappear
 * until the next update. The check runs once per session.
 *
 * `shouldShowWhatsNew` is the pure decision (tested in useWhatsNew.test.ts); the
 * hook is the impure shell that reads config, parses the changelog, and persists.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { getVersion } from "@tauri-apps/api/app";

import changelog from "/CHANGELOG.md?raw";
import semverGt from "semver/functions/gt";

import { useAppConfig } from "../state/appConfig";
import {
  normVersion,
  parseChangelog,
  sectionsSince,
  type ChangelogVersion,
} from "../lib/changelog";

/**
 * Pure: should the "What's new" modal open? False on a first-ever launch
 * (no lastSeen) and when the running version is at or below what was last seen.
 * Prerelease tags are kept in the comparison so 0.3.0-beta.1 → 0.3.0-beta.2
 * counts as a newer build. True only when the user is on a strictly newer build.
 */
export function shouldShowWhatsNew(lastSeen: string | null, current: string): boolean {
  if (lastSeen === null) return false;
  return semverGt(normVersion(current), normVersion(lastSeen));
}

export interface UseWhatsNewResult {
  /** Whether the modal should be shown. */
  open: boolean;
  /** The running app version (e.g. "0.3.0"); "" until resolved. */
  current: string;
  /** The changelog sections added since the last launch, newest first. */
  sections: ChangelogVersion[];
  /** Record the current version as seen and close the modal. */
  dismiss: () => void;
}

export function useWhatsNew(): UseWhatsNewResult {
  const { config, loading, setFlag } = useAppConfig();

  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [sections, setSections] = useState<ChangelogVersion[]>([]);

  // Guards: run the gate once per session, and avoid setState after unmount.
  const checkedOnce = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // The post-update gate: once, after config settles.
  useEffect(() => {
    if (loading || checkedOnce.current) return;
    checkedOnce.current = true;

    void (async () => {
      const version = await getVersion();
      if (!mounted.current) return;
      setCurrent(version);

      const lastSeen = config.lastSeenVersion;

      // First ever launch: nothing to show, but record where we are so the next
      // update has a baseline.
      if (lastSeen === null) {
        setFlag("lastSeenVersion", version);
        return;
      }

      if (!shouldShowWhatsNew(lastSeen, version)) return;

      const since = sectionsSince(parseChangelog(changelog), lastSeen, version);
      if (since.length === 0) return;

      setSections(since);
      setOpen(true);
    })();
  }, [loading, config.lastSeenVersion, setFlag]);

  const dismiss = useCallback(() => {
    if (current) setFlag("lastSeenVersion", current);
    setOpen(false);
  }, [current, setFlag]);

  return { open, current, sections, dismiss };
}
