import { type ReactNode, isValidElement } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate, type NavigateFunction } from "react-router-dom";
import { openUrl } from "@tauri-apps/plugin-opener";
import { Info, TriangleAlert } from "lucide-react";

import { slugifyHeading } from "../../lib/docs";

/** Flatten React children to plain text (for heading ids and alert detection). */
function textOf(node: ReactNode): string {
  if (node == null || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children);
  return "";
}

/** Smooth-scroll to a heading without touching the hash-router URL. */
function scrollToId(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

const ALERT = /^\[!(NOTE|TIP|WARNING)\]\s*/;
const ALERT_STYLE = {
  NOTE: { label: "Note", cls: "border-accent-line bg-accent-tint", icon: Info, ic: "bg-accent" },
  TIP: { label: "Tip", cls: "border-amber/40 bg-amber/10", icon: Info, ic: "bg-amber" },
  WARNING: {
    label: "Warning",
    cls: "border-amber/40 bg-amber/10",
    icon: TriangleAlert,
    ic: "bg-amber",
  },
} as const;

function Heading({ level, children }: { level: 2 | 3; children: ReactNode }) {
  const id = slugifyHeading(textOf(children));
  const cls =
    level === 2
      ? "group mb-3 mt-9 scroll-mt-6 text-[1.15rem] font-bold tracking-snug text-ink"
      : "mb-2 mt-6 scroll-mt-6 text-[0.95rem] font-bold tracking-snug text-ink";
  const Tag = level === 2 ? "h2" : "h3";
  return (
    <Tag id={id} className={cls}>
      {children}
      <a
        href={`#${id}`}
        aria-label="Link to this section"
        onClick={(e) => {
          e.preventDefault();
          scrollToId(id);
        }}
        className="ml-2 text-accent opacity-0 transition-opacity group-hover:opacity-70"
      >
        #
      </a>
    </Tag>
  );
}

function makeComponents(navigate: NavigateFunction): Components {
  return {
    h1: ({ children }) => <h2 className="mb-3 mt-9 text-[1.15rem] font-bold text-ink">{children}</h2>,
    h2: ({ children }) => <Heading level={2}>{children}</Heading>,
    h3: ({ children }) => <Heading level={3}>{children}</Heading>,
    p: ({ children }) => <p className="mb-3.5 text-body leading-relaxed text-ink-2">{children}</p>,
    a: ({ href = "", children }) => {
      const external = /^https?:\/\//.test(href);
      const hash = href.startsWith("#");
      return (
        <a
          href={href}
          onClick={(e) => {
            e.preventDefault();
            if (external) void openUrl(href);
            else if (hash) scrollToId(href.slice(1));
            else navigate(href);
          }}
          className="border-b border-accent-line text-accent transition-colors hover:border-accent"
        >
          {children}
          {external && <span className="ml-0.5 align-super text-[0.7em] opacity-70">↗</span>}
        </a>
      );
    },
    ul: ({ children }) => (
      <ul className="mb-4 list-disc space-y-2 pl-5 text-body text-ink-2 marker:text-accent">
        {children}
      </ul>
    ),
    ol: ({ children }) => (
      <ol className="mb-4 list-decimal space-y-2 pl-5 text-body text-ink-2 marker:font-mono marker:text-caption marker:text-accent">
        {children}
      </ol>
    ),
    li: ({ children }) => (
      <li className="text-body leading-relaxed text-ink-2">{children}</li>
    ),
    code: ({ className, children }) => {
      const text = String(children ?? "");
      const block = /language-/.test(className ?? "") || text.includes("\n");
      if (block) return <code className="font-mono text-caption text-term-ink">{children}</code>;
      return (
        <code className="rounded border border-line-2 bg-surface-2 px-1.5 py-0.5 font-mono text-[0.72rem] text-ink">
          {children}
        </code>
      );
    },
    pre: ({ children }) => (
      <pre className="mb-4.5 overflow-x-auto rounded-panel bg-term p-4 font-mono text-caption leading-relaxed text-term-ink shadow-card">
        {children}
      </pre>
    ),
    blockquote: ({ children }) => {
      const text = textOf(children).trim();
      const m = text.match(ALERT);
      if (!m) {
        return (
          <blockquote className="my-4 border-l-2 border-line-2 pl-4 text-body italic text-ink-2">
            {children}
          </blockquote>
        );
      }
      const a = ALERT_STYLE[m[1] as keyof typeof ALERT_STYLE];
      const Icon = a.icon;
      const bodyText = text.replace(ALERT, "").trim();
      return (
        <div className={`my-4.5 flex gap-3 rounded-panel border px-4 py-3.5 ${a.cls}`}>
          <span
            className={`mt-0.5 grid h-4.5 w-4.5 shrink-0 place-items-center rounded-md text-white ${a.ic}`}
          >
            <Icon size={12} strokeWidth={2.4} />
          </span>
          <div>
            <div className="mb-0.5 text-micro font-bold uppercase tracking-eyebrow text-ink-2">
              {a.label}
            </div>
            <div className="text-body leading-snug text-ink-2">{bodyText}</div>
          </div>
        </div>
      );
    },
    table: ({ children }) => (
      <div className="my-4.5 overflow-hidden rounded-panel border border-line-2">
        <table className="w-full border-collapse text-caption">{children}</table>
      </div>
    ),
    th: ({ children }) => (
      <th className="border-b border-line-2 bg-surface-2 px-3.5 py-2.5 text-left font-semibold text-ink">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="border-b border-line px-3.5 py-2.5 text-ink-2">{children}</td>
    ),
    hr: () => <hr className="my-7 border-line" />,
    img: ({ src = "", alt = "" }) => (
      <img src={src} alt={alt} className="my-4 rounded-panel border border-line-2 shadow-card" />
    ),
  };
}

/** Render a markdown string with the docs styling, on the app design tokens. */
export function Markdown({ source }: { source: string }) {
  const navigate = useNavigate();
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={makeComponents(navigate)}>
      {source}
    </ReactMarkdown>
  );
}
