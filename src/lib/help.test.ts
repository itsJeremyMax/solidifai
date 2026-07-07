import { describe, expect, it } from "vitest";

import { buildIssueUrl, HELP_CATEGORIES, type IssueDraft } from "./help";

const BASE: IssueDraft = {
  category: "bug",
  title: "Viewport stays empty",
  details: "Asked for a 20mm cube, nothing rendered.",
  version: "0.3.0",
  os: "macOS",
  diagnostics: "solidifai   0.3.0\nOS          macOS",
  includeDiagnostics: true,
};

/** Parse the URL and return its decoded query params for assertions. */
function params(url: string): URLSearchParams {
  return new URL(url).searchParams;
}

describe("buildIssueUrl", () => {
  it("routes a bug report to the bug form and prefills its fields", () => {
    const q = params(buildIssueUrl(BASE));
    expect(q.get("template")).toBe("bug_report.yml");
    expect(q.get("title")).toBe("Viewport stays empty");
    expect(q.get("what-happened")).toBe("Asked for a 20mm cube, nothing rendered.");
    expect(q.get("version")).toBe("0.3.0");
    // diagnostics land in the form's logs field, fenced for monospace rendering
    expect(q.get("logs")).toContain("solidifai   0.3.0");
    expect(q.get("logs")).toContain("```");
    // it points at the repo's issue tracker
    expect(buildIssueUrl(BASE)).toContain("github.com/itsJeremyMax/solidifai/issues/new");
  });

  it("prefills the OS dropdown only when it matches a form option", () => {
    expect(params(buildIssueUrl({ ...BASE, os: "Windows" })).get("os")).toBe("Windows");
    expect(params(buildIssueUrl({ ...BASE, os: "Linux" })).get("os")).toBe("Linux");
    // macOS can't be disambiguated (Apple Silicon vs Intel), so it's left unset
    expect(params(buildIssueUrl({ ...BASE, os: "macOS" })).has("os")).toBe(false);
  });

  it("omits system info from the bug form when the user opts out", () => {
    const q = params(buildIssueUrl({ ...BASE, includeDiagnostics: false }));
    expect(q.has("logs")).toBe(false);
    expect(q.get("what-happened")).toBe("Asked for a 20mm cube, nothing rendered.");
  });

  it("routes a feature request to the feature form", () => {
    const q = params(buildIssueUrl({ ...BASE, category: "feature", details: "Add dark mode" }));
    expect(q.get("template")).toBe("feature_request.yml");
    expect(q.get("problem")).toBe("Add dark mode");
    expect(q.has("version")).toBe(false); // the feature form has no version field
  });

  it("opens a blank labelled issue for a question, with fenced diagnostics in the body", () => {
    const q = params(
      buildIssueUrl({ ...BASE, category: "question", details: "How do I export STEP?" }),
    );
    expect(q.has("template")).toBe(false);
    expect(q.get("labels")).toBe("question");
    expect(q.get("body")).toContain("How do I export STEP?");
    expect(q.get("body")).toContain("```");
    expect(q.get("body")).toContain("solidifai   0.3.0");
  });

  it("opens a blank unlabelled issue for 'other'", () => {
    const q = params(buildIssueUrl({ ...BASE, category: "other", includeDiagnostics: false }));
    expect(q.has("template")).toBe(false);
    expect(q.has("labels")).toBe(false);
    expect(q.get("body")).toBe("Asked for a 20mm cube, nothing rendered.");
  });

  it("trims whitespace and drops empty fields", () => {
    const q = params(buildIssueUrl({ ...BASE, title: "   ", details: "  real content  " }));
    expect(q.has("title")).toBe(false);
    expect(q.get("what-happened")).toBe("real content");
  });

  it("exposes a category for each reporting option", () => {
    expect(HELP_CATEGORIES.map((c) => c.value)).toEqual(["bug", "feature", "question", "other"]);
  });
});
