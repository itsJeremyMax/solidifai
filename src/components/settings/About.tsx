/**
 * About — the "About" settings section. Identity block (logo + wordmark, version,
 * license, creator), a short "what's new" card, and a copyable diagnostics table.
 *
 * The version is read live via getVersion(), which resolves to the single source
 * of truth (root package.json) through tauri.conf.json's "version": "../package.json".
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Copy, ExternalLink } from "lucide-react";

import changelog from "/CHANGELOG.md?raw";

import {
  buildDiagnostics,
  copyText,
  CREATOR,
  diagnosticRows,
  LICENSE,
  loadAppInfo,
  openLicense,
  type AppInfo,
} from "../../lib/appInfo";
import {
  nonEmptyGroups,
  normVersion,
  parseChangelog,
  type ChangelogVersion,
} from "../../lib/changelog";
import ReleaseNotesGroups from "../ReleaseNotesGroups";

const ICON_STROKE = 1.7;

/**
 * The changelog section for the running version — the real, per-release "What's
 * new", sourced from the same bundled CHANGELOG.md the post-update modal uses so
 * it can never go stale. Falls back to the newest section when the exact version
 * isn't in the changelog yet (e.g. a dev build ahead of the last release).
 */
function whatsNewFor(version: string): ChangelogVersion | undefined {
  const sections = parseChangelog(changelog);
  return sections.find((s) => normVersion(s.version) === normVersion(version)) ?? sections[0];
}

/** One labelled fact in the identity strip. */
function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-micro uppercase tracking-eyebrow text-ink-3">{label}</div>
      <div className="mt-0.75 truncate text-body font-medium text-ink">{children}</div>
    </div>
  );
}

/** One diagnostics key/value row. */
function DiagRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-4 px-4 py-2.5">
      <span className="w-24 shrink-0 text-caption text-ink-3">{label}</span>
      <span className="min-w-0 flex-1 truncate text-right font-mono text-caption text-ink">
        {value}
      </span>
    </div>
  );
}

export default function About() {
  const [info, setInfo] = useState<AppInfo | null>(null); // null = loading
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadAppInfo().then((i) => {
      if (!cancelled) setInfo(i);
    });
    return () => {
      cancelled = true;
      if (copyTimer.current) clearTimeout(copyTimer.current);
    };
  }, []);

  const handleCopy = async () => {
    if (!info) return;
    const ok = await copyText(buildDiagnostics(info));
    if (!ok) return;
    setCopied(true);
    if (copyTimer.current) clearTimeout(copyTimer.current);
    copyTimer.current = setTimeout(() => setCopied(false), 2000);
  };

  const version = info?.version ?? "…";

  // One row source for the table and the copied block (appInfo.diagnosticRows),
  // so what's shown and what's copied can't drift. App-scoped: no workspace row.
  const diagnostics = info ? diagnosticRows(info) : [];

  // Real per-release notes for the running version; hidden until the version
  // resolves and only when the section actually has entries.
  const whatsNew = useMemo(() => (info ? whatsNewFor(info.version) : undefined), [info]);
  const hasNotes = whatsNew ? nonEmptyGroups(whatsNew.groups).length > 0 : false;

  return (
    <div className="mx-auto max-w-160 py-6.5">
      {/* Identity */}
      <div className="overflow-hidden rounded-panel border border-line bg-surface shadow-card">
        <div className="flex items-center gap-4 bg-sheen p-5">
          <img
            src="/logo.png"
            alt=""
            draggable={false}
            className="h-14 w-14 shrink-0 select-none rounded-xl border border-line-2"
          />
          <div className="min-w-0">
            <div className="text-xl font-bold tracking-snug text-ink">solidifai</div>
            <div className="mt-0.5 text-body text-ink-2">Agentic parametric CAD.</div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 border-t border-line px-5 py-4">
          <Fact label="Version">
            <span className="font-mono">{version}</span>
          </Fact>
          <Fact label="License">
            <button
              type="button"
              onClick={() => void openLicense()}
              title="View the full license"
              className="group inline-flex max-w-full items-center gap-1.25 truncate text-accent transition-colors duration-150 hover:text-accent-press"
            >
              <span className="truncate">{LICENSE}</span>
              <ExternalLink
                size={12}
                strokeWidth={2}
                className="shrink-0 opacity-70 transition-opacity duration-150 group-hover:opacity-100"
              />
            </button>
          </Fact>
          <Fact label="Created by">{CREATOR}</Fact>
        </div>
      </div>

      {/* What's new — real notes for this release, grouped like the changelog. */}
      {whatsNew && hasNotes && (
        <div className="mt-5">
          <div className="mb-2 flex items-center gap-2">
            <h2 className="text-base font-bold tracking-snug text-ink">What's new</h2>
            <span className="rounded-full bg-accent-tint px-2 py-0.5 font-mono text-micro font-semibold tracking-[0.04em] text-accent">
              {version}
            </span>
          </div>
          <ReleaseNotesGroups groups={whatsNew.groups} />
        </div>
      )}

      {/* Diagnostics */}
      <div className="mt-5">
        <div className="mb-2 flex items-center gap-2.5">
          <h2 className="text-base font-bold tracking-snug text-ink">Diagnostics</h2>
          <div className="flex-1" />
          {copied && <span className="font-mono text-caption text-engine">Copied</span>}
          <button
            type="button"
            onClick={() => void handleCopy()}
            disabled={!info}
            title="Copy diagnostics for a bug report"
            className="inline-flex h-8 items-center gap-1.75 rounded-lg border border-line-2 bg-surface px-3 text-body font-medium text-ink-2 transition-colors duration-150 hover:border-line-3 hover:text-ink disabled:opacity-40 disabled:hover:border-line-2 disabled:hover:text-ink-2"
          >
            {copied ? (
              <Check size={14} strokeWidth={2.2} className="text-engine" />
            ) : (
              <Copy size={14} strokeWidth={ICON_STROKE} />
            )}
            Copy
          </button>
        </div>
        <div className="divide-y divide-line overflow-hidden rounded-panel border border-line bg-surface">
          {info === null ? (
            <div className="px-4 py-3 text-body text-ink-3">Loading…</div>
          ) : (
            diagnostics.map(([k, v]) => <DiagRow key={k} label={k} value={v} />)
          )}
        </div>
      </div>
    </div>
  );
}
