import type { ReactNode } from "react";

/**
 * One-line description for a library page. Sits at the top of the body, above the
 * section eyebrow, giving the page name (shown in the header crumb) a plain-language
 * "what this is for". Keep the copy to a single line: this is a lead, not a manual.
 */
export default function PageIntro({ children }: { children: ReactNode }) {
  return <p className="mb-5 max-w-160 text-body leading-relaxed text-ink-2">{children}</p>;
}
