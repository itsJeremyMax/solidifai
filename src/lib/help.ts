/**
 * help — pure logic behind the Help page's "open a GitHub issue" action.
 *
 * The repo ships issue *forms* (.github/ISSUE_TEMPLATE/bug_report.yml and
 * feature_request.yml) plus allows blank issues. So we prefill the matching form
 * for bugs and feature requests (mapping our fields onto the form's field ids, and
 * auto-filling the version/OS the form asks for), and fall back to a blank issue
 * for questions and anything else. GitHub reads form-field prefills from query
 * params keyed by each field's `id`; a value that doesn't match (e.g. an OS we
 * can't disambiguate) is silently ignored, so partial prefill is always safe.
 *
 * The engine mirrors this same field-id contract in
 * engine/solidifai_engine/issue.py for Sol's terminal path; keep the two in sync.
 */
import { ISSUES_URL } from "./appInfo";

export type HelpCategory = "bug" | "feature" | "question" | "other";

export interface HelpCategoryDef {
  value: HelpCategory;
  label: string;
  /** The label + placeholder for the free-text field, tuned per category. */
  detailLabel: string;
  detailPlaceholder: string;
}

/** The reporting categories offered on the Help page, in order. */
export const HELP_CATEGORIES: HelpCategoryDef[] = [
  {
    value: "bug",
    label: "Bug report",
    detailLabel: "What happened?",
    detailPlaceholder: "What did you do, what did you expect, and what happened instead?",
  },
  {
    value: "feature",
    label: "Feature request",
    detailLabel: "What problem would this solve?",
    detailPlaceholder: "Describe where solidifai falls short today, and what you'd like instead.",
  },
  {
    value: "question",
    label: "Question",
    detailLabel: "Your question",
    detailPlaceholder: "Ask away. Include what you've already tried.",
  },
  {
    value: "other",
    label: "Something else",
    detailLabel: "Details",
    detailPlaceholder: "Tell us what's on your mind.",
  },
];

/** The bug form's OS dropdown options we can match from the webview UA. macOS is
 *  omitted on purpose: Apple Silicon vs Intel isn't knowable here, so the user
 *  picks it on the form rather than us guessing wrong. */
function osDropdownOption(os: string): string | null {
  if (os === "Windows") return "Windows";
  if (os === "Linux") return "Linux";
  return null;
}

/** Wrap a diagnostics block in a fenced code block so it renders monospaced. */
function fence(text: string): string {
  return `\`\`\`\n${text}\n\`\`\``;
}

export interface IssueDraft {
  category: HelpCategory;
  title: string;
  /** The main free-text field (maps to the form's primary textarea). */
  details: string;
  /** solidifai version for the bug form's version field ("" when unknown). */
  version: string;
  /** OS family label from appInfo (osLabel()). */
  os: string;
  /** Full diagnostics block, attached where a form or body has room for it. */
  diagnostics: string;
  /** When false, no system info is attached anywhere. */
  includeDiagnostics: boolean;
}

const NEW_ISSUE = `${ISSUES_URL}/new`;

/**
 * Build a GitHub "new issue" URL that prefills everything we know. Bugs and
 * feature requests target the repo's issue forms (preserving the maintainer's
 * structure and pre-filling version/OS); questions and anything else open a blank
 * issue, which the repo allows. Every value is URL-encoded via URLSearchParams.
 */
export function buildIssueUrl(draft: IssueDraft): string {
  const { category, version, os, diagnostics, includeDiagnostics } = draft;
  const title = draft.title.trim();
  const details = draft.details.trim();
  const p = new URLSearchParams();
  if (title) p.set("title", title);

  if (category === "bug") {
    p.set("template", "bug_report.yml");
    if (details) p.set("what-happened", details);
    if (version) p.set("version", version);
    const osOpt = osDropdownOption(os);
    if (osOpt) p.set("os", osOpt);
    if (includeDiagnostics && diagnostics) p.set("logs", fence(diagnostics));
    return `${NEW_ISSUE}?${p.toString()}`;
  }

  if (category === "feature") {
    p.set("template", "feature_request.yml");
    if (details) p.set("problem", details);
    return `${NEW_ISSUE}?${p.toString()}`;
  }

  // question / other -> blank issue. Category rides along as a label (question)
  // and the diagnostics, when included, are appended to the body.
  if (category === "question") p.set("labels", "question");
  let body = details;
  if (includeDiagnostics && diagnostics) {
    body = body ? `${body}\n\n---\n${fence(diagnostics)}` : fence(diagnostics);
  }
  if (body) p.set("body", body);
  return `${NEW_ISSUE}?${p.toString()}`;
}
