/**
 * changelog — a tiny, dependency-light parser for the release-please CHANGELOG.md
 * format, plus a helper that selects the version sections added since the user
 * last launched. Powers the post-update "What's new" screen.
 *
 * The parser is intentionally forgiving: it reads `## [x.y.z](link) (date)`
 * version headers, `### Group` subheaders (Features, Bug Fixes, …), and `* entry`
 * bullets. It normalizes the real release-please bullet form
 * `* **scope:** message ([abc1234](url))` into plain `scope: message` by
 * stripping the trailing commit/PR links and the bold markers.
 */
import semverGt from "semver/functions/gt";
import semverLte from "semver/functions/lte";
import semverCoerce from "semver/functions/coerce";
import semverParse from "semver/functions/parse";

export interface ChangelogVersion {
  version: string;
  date?: string;
  groups: Record<string, string[]>;
}

const VERSION_RE = /^##\s+\[?(\d+\.\d+\.\d+(?:-[\w.]+)?)\]?.*?(?:\((\d{4}-\d{2}-\d{2})\))?\s*$/;
const GROUP_RE = /^###\s+(.+?)\s*$/;
const ENTRY_RE = /^\*\s+(.+?)\s*$/;

/**
 * Clean a release-please bullet: drop any trailing `([label](url))` link groups
 * (commit and/or PR) and any bare `(sha)`, strip `**bold**` markers so a
 * `**scope:**` prefix renders as plain `scope:`, and decode the HTML entities
 * release-please escapes in commit subjects (e.g. `->` becomes `-&gt;`), since
 * entries render as plain text, not HTML. `&amp;` must decode last so a
 * double-escaped entity doesn't decode twice.
 */
function cleanEntry(s: string): string {
  let out = s.trim();
  let prev: string;
  do {
    prev = out;
    out = out
      .replace(/\s*\(\[[^\]]+\]\([^)]*\)\)\s*$/, "") // ([label](url))
      .replace(/\s*\([0-9a-f]{6,}\)\s*$/, "") // bare (sha)
      .trim();
  } while (out !== prev);
  return out
    .replace(/\*\*/g, "")
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&")
    .trim();
}

/**
 * Drop a leading version/title heading (a top-level `#`/`##` line, plus any blank
 * lines before it) from release notes, so a surface that prints its own "What's
 * new in vX" title never doubles it. Group subheaders (`###`) and everything else
 * are kept. A no-op when the notes already start with content.
 */
export function stripLeadingTitle(md: string): string {
  const lines = md.split("\n");
  let i = 0;
  while (i < lines.length && lines[i].trim() === "") i++;
  if (i < lines.length && /^#{1,2}\s/.test(lines[i])) i++;
  return lines.slice(i).join("\n").trim();
}

/**
 * The non-empty groups of a parsed section (`Features`, `Bug Fixes`, …), in
 * display order. Used to decide whether a version has anything worth showing and
 * to drive the grouped release-notes rendering.
 */
export function nonEmptyGroups(groups: Record<string, string[]>): [string, string[]][] {
  return Object.entries(groups).filter(([, entries]) => entries.length > 0);
}

export function parseChangelog(md: string): ChangelogVersion[] {
  const out: ChangelogVersion[] = [];
  let cur: ChangelogVersion | null = null;
  let group = "";
  for (const line of md.split("\n")) {
    const v = VERSION_RE.exec(line);
    if (v) {
      cur = { version: v[1], date: v[2], groups: {} };
      out.push(cur);
      group = "";
      continue;
    }
    if (!cur) continue;
    const g = GROUP_RE.exec(line);
    if (g) {
      group = g[1];
      cur.groups[group] = cur.groups[group] ?? [];
      continue;
    }
    const e = ENTRY_RE.exec(line);
    if (e && group) cur.groups[group].push(cleanEntry(e[1]));
  }
  return out;
}

/**
 * Normalize a version string for comparison, keeping any prerelease tag.
 * Coercing would strip "-beta.2", collapsing consecutive beta builds into the
 * same version; coerce stays only as the fallback for loose strings parse
 * rejects.
 */
export function normVersion(v: string): string {
  return semverParse(v)?.version ?? semverCoerce(v)?.version ?? v;
}

export function sectionsSince(
  versions: ChangelogVersion[],
  lastSeen: string | null,
  current: string,
): ChangelogVersion[] {
  const cur = normVersion(current);
  return versions.filter((v) => {
    const ver = normVersion(v.version);
    const inUpper = semverLte(ver, cur);
    const inLower = lastSeen ? semverGt(ver, normVersion(lastSeen)) : true;
    return inUpper && inLower;
  });
}
