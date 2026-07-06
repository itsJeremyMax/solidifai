import { useMemo } from "react";
import { Navigate, useParams, Link } from "react-router-dom";

import { DOC_PAGES, getDoc, extractHeadings, slugifyHeading } from "../../lib/docs";
import { Markdown } from "./Markdown";
import { useActiveHeading } from "./tocObserver";

/**
 * DocPage - one documentation page in a measured reading column, with an
 * "On this page" rail on the right (driven by the body headings) and a
 * previous/next footer from the registry order. An unknown slug redirects to the
 * first page so a stale link never dead-ends.
 */
export default function DocPage() {
  const { slug = "" } = useParams();
  const doc = getDoc(slug);
  const idx = DOC_PAGES.findIndex((d) => d.slug === slug);
  const headings = useMemo(() => (doc ? extractHeadings(doc.body) : []), [doc]);
  const ids = useMemo(() => headings.map(slugifyHeading), [headings]);
  const active = useActiveHeading(ids);

  if (!doc) return <Navigate to={`/docs/${DOC_PAGES[0]?.slug ?? ""}`} replace />;

  const prev = idx > 0 ? DOC_PAGES[idx - 1] : null;
  const next = idx >= 0 && idx < DOC_PAGES.length - 1 ? DOC_PAGES[idx + 1] : null;

  return (
    <div className="flex min-h-0 flex-1">
      <article className="min-w-0 flex-1 overflow-y-auto bg-[radial-gradient(120%_50%_at_50%_0,#fdfdfc,transparent_55%)] px-12 pb-16 pt-10">
        <div className="mx-auto max-w-160">
          <div className="mb-3 text-micro font-bold uppercase tracking-eyebrow text-accent">
            {doc.group}
          </div>
          <h1 className="mb-3.5 text-[1.85rem] font-extrabold leading-tight tracking-snug text-ink">
            {doc.title}
          </h1>
          {doc.description && (
            <p className="mb-7 text-[0.95rem] leading-relaxed text-ink-2">{doc.description}</p>
          )}

          <Markdown source={doc.body} />

          {(prev || next) && (
            <nav className="mt-10 flex justify-between gap-3 border-t border-line pt-5">
              {prev ? (
                <Link
                  to={`/docs/${prev.slug}`}
                  className="flex-1 rounded-panel border border-line-2 px-3.5 py-3 transition-colors hover:border-line-3"
                >
                  <div className="text-micro uppercase tracking-eyebrow text-ink-3">Previous</div>
                  <div className="text-body font-semibold text-ink">{prev.title}</div>
                </Link>
              ) : (
                <span className="flex-1" />
              )}
              {next ? (
                <Link
                  to={`/docs/${next.slug}`}
                  className="flex-1 rounded-panel border border-line-2 px-3.5 py-3 text-right transition-colors hover:border-line-3"
                >
                  <div className="text-micro uppercase tracking-eyebrow text-ink-3">Next</div>
                  <div className="text-body font-semibold text-ink">{next.title}</div>
                </Link>
              ) : (
                <span className="flex-1" />
              )}
            </nav>
          )}
        </div>
      </article>

      {headings.length > 0 && (
        <aside className="hidden w-53 shrink-0 overflow-y-auto border-l border-line bg-surface px-5 py-10 lg:block">
          <div className="mb-3.5 text-micro font-bold uppercase tracking-eyebrow text-ink-3">
            On this page
          </div>
          {headings.map((h, i) => (
            <a
              key={ids[i]}
              href={`#${ids[i]}`}
              onClick={(e) => {
                e.preventDefault();
                document.getElementById(ids[i])?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
              className={`block border-l-2 py-1.5 pl-3 text-caption leading-snug transition-colors ${
                active === ids[i]
                  ? "border-accent font-semibold text-accent"
                  : "border-line-2 text-ink-3 hover:text-ink-2"
              }`}
            >
              {h}
            </a>
          ))}
        </aside>
      )}
    </div>
  );
}
