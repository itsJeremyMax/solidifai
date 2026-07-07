/**
 * ReleaseNotes — renders update release notes (markdown) with Tailwind-only
 * element styles, so no global CSS. Shared by the update card's popover/toast and
 * the Settings → Updates "What's new" section, so notes look identical wherever
 * they appear.
 */
import type { ComponentProps, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { stripLeadingTitle } from "../../lib/changelog";

function Heading({ children }: { children: ReactNode }) {
  return (
    <div className="mb-1.5 text-micro font-semibold uppercase tracking-eyebrow text-ink-3">
      {children}
    </div>
  );
}

const COMPONENTS: ComponentProps<typeof ReactMarkdown>["components"] = {
  h1: ({ children }) => <Heading>{children}</Heading>,
  h2: ({ children }) => <Heading>{children}</Heading>,
  h3: ({ children }) => <Heading>{children}</Heading>,
  ul: ({ children }) => <ul className="grid gap-1.5">{children}</ul>,
  li: ({ children }) => (
    <li className="relative pl-3.5 before:absolute before:left-0.25 before:top-1.75 before:h-1.25 before:w-1.25 before:rounded-full before:bg-accent/70 before:content-['']">
      {children}
    </li>
  ),
  p: ({ children }) => <p className="mb-1.5 last:mb-0">{children}</p>,
  a: ({ children, href }) => (
    <a href={href} className="text-accent underline-offset-2 hover:underline">
      {children}
    </a>
  ),
};

export default function ReleaseNotes({
  notes,
  className = "",
}: {
  notes: string;
  className?: string;
}) {
  return (
    <div className={`text-caption leading-normal text-ink-2 ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {stripLeadingTitle(notes)}
      </ReactMarkdown>
    </div>
  );
}
