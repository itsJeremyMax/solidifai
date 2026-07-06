import { describe, it, expect } from "vitest";
import { parseChangelog, sectionsSince } from "./changelog";

// The real release-please format: compare-URL version headers, `**scope:**` bold
// prefixes, and trailing commit (and sometimes PR) markdown links.
const SAMPLE = `# Changelog

## [0.3.0](https://github.com/itsJeremyMax/solidifai/compare/v0.2.0...v0.3.0) (2026-06-04)

### Features
* **updater:** channel toggle ([abc1234](https://github.com/itsJeremyMax/solidifai/commit/abc1234def567))
* **brief:** bump engine protocol 6 -&gt; 7 &amp; add &quot;plan&quot; panel ([abc1234](https://github.com/itsJeremyMax/solidifai/commit/abc1234def567))

### Bug Fixes
* **viewport:** explode drift ([#42](https://github.com/itsJeremyMax/solidifai/issues/42)) ([def5678](https://github.com/itsJeremyMax/solidifai/commit/def5678abc901))

## [0.2.0](https://github.com/itsJeremyMax/solidifai/compare/v0.1.0...v0.2.0) (2026-05-20)

### Features
* **dfm:** rules engine ([ghi9012](https://github.com/itsJeremyMax/solidifai/commit/ghi9012jkl345))
`;

describe("parseChangelog", () => {
  it("parses versions, dates, and grouped entries (bold + links stripped)", () => {
    const v = parseChangelog(SAMPLE);
    expect(v.map((x) => x.version)).toEqual(["0.3.0", "0.2.0"]);
    expect(v[0].groups["Features"]).toEqual([
      "updater: channel toggle",
      'brief: bump engine protocol 6 -> 7 & add "plan" panel',
    ]);
    expect(v[0].groups["Bug Fixes"]).toEqual(["viewport: explode drift"]);
    // no leftover markdown link or bold syntax leaks into the rendered entry
    expect(v[0].groups["Features"][0]).not.toMatch(/[*[\]()]|https?:/);
  });
});

describe("sectionsSince", () => {
  it("returns versions in (lastSeen, current]", () => {
    const v = parseChangelog(SAMPLE);
    expect(sectionsSince(v, "0.2.0", "0.3.0").map((x) => x.version)).toEqual(["0.3.0"]);
  });
  it("includes everything when lastSeen is null", () => {
    const v = parseChangelog(SAMPLE);
    expect(sectionsSince(v, null, "0.3.0").map((x) => x.version)).toEqual(["0.3.0", "0.2.0"]);
  });
  it("empty when up to date", () => {
    const v = parseChangelog(SAMPLE);
    expect(sectionsSince(v, "0.3.0", "0.3.0")).toEqual([]);
  });
  it("keeps prerelease tags apart instead of coercing them equal", () => {
    const beta = `# Changelog

## [0.3.0-beta.2](https://github.com/itsJeremyMax/solidifai/compare/v0.3.0-beta.1...v0.3.0-beta.2) (2026-06-05)

### Bug Fixes
* **updater:** beta manifest 404 ([abc1234](https://github.com/itsJeremyMax/solidifai/commit/abc1234def567))

## [0.3.0-beta.1](https://github.com/itsJeremyMax/solidifai/compare/v0.2.0...v0.3.0-beta.1) (2026-06-04)

### Features
* **updater:** channel toggle ([def5678](https://github.com/itsJeremyMax/solidifai/commit/def5678abc901))
`;
    const v = parseChangelog(beta);
    expect(sectionsSince(v, "0.3.0-beta.1", "0.3.0-beta.2").map((x) => x.version)).toEqual([
      "0.3.0-beta.2",
    ]);
    expect(sectionsSince(v, "0.3.0-beta.2", "0.3.0-beta.2")).toEqual([]);
  });
});
