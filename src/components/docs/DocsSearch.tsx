import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";

import { DOC_SEARCH, type SearchEntry } from "../../lib/docs";

/**
 * The field lives in the persistent AppHeader (published via the header slot),
 * which renders outside the routed DocsLayout where the provider is mounted. A
 * window event, rather than React context, lets the field open the palette
 * across that boundary. Cmd/Ctrl+K uses the same path.
 */
const OPEN_EVENT = "docs-search:open";

/** Rank entries by where the query hits: title beats heading beats body. */
function rank(entries: SearchEntry[], q: string): SearchEntry[] {
  const t = q.trim().toLowerCase();
  if (!t) return entries.slice(0, 8);
  return entries
    .map((e) => {
      const inTitle = e.title.toLowerCase().includes(t);
      const inHead = e.headings.some((h) => h.toLowerCase().includes(t));
      const inText = e.text.includes(t);
      const score = (inTitle ? 3 : 0) + (inHead ? 2 : 0) + (inText ? 1 : 0);
      return { e, score };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((x) => x.e);
}

/**
 * Provides the docs search palette and an open() trigger to descendants. The
 * palette is client-side over the bundled doc index, opens from the header field
 * or Cmd/Ctrl+K, and navigates on select. Must live inside the router (it uses
 * navigate), which it does as a child of the routed DocsLayout.
 */
export function DocsSearchProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const navigate = useNavigate();
  const results = useMemo(() => rank(DOC_SEARCH, q), [q]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === "Escape") setOpen(false);
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_EVENT, onOpen);
    };
  }, []);

  useEffect(() => setSel(0), [q]);

  const go = (slug: string) => {
    setOpen(false);
    setQ("");
    navigate(`/docs/${slug}`);
  };

  return (
    <>
      {children}
      {isOpen && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-scrim pt-[12vh]"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-[min(560px,92vw)] overflow-hidden rounded-panel border border-line-2 bg-surface shadow-float"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2.5 border-b border-line px-4">
              <Search size={16} className="text-ink-3" />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") setSel((s) => Math.min(s + 1, results.length - 1));
                  if (e.key === "ArrowUp") setSel((s) => Math.max(s - 1, 0));
                  if (e.key === "Enter" && results[sel]) go(results[sel].slug);
                }}
                placeholder="Search the docs"
                className="h-12 flex-1 bg-transparent text-body text-ink outline-none placeholder:text-ink-3"
              />
            </div>
            <div className="max-h-80 overflow-y-auto p-1.5">
              {results.length === 0 ? (
                <div className="px-3 py-6 text-center text-body text-ink-3">No matches</div>
              ) : (
                results.map((r, i) => (
                  <button
                    key={r.slug}
                    type="button"
                    onMouseEnter={() => setSel(i)}
                    onClick={() => go(r.slug)}
                    className={`flex w-full flex-col items-start rounded-lg px-3 py-2 text-left ${
                      i === sel ? "bg-accent-tint" : "hover:bg-surface-hover"
                    }`}
                  >
                    <span className="text-body font-medium text-ink">{r.title}</span>
                    <span className="text-caption text-ink-3">
                      {r.group}
                      {r.description ? ` · ${r.description}` : ""}
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/** Breathing room required between a true-centered search and the side clusters. */
const CENTER_GAP = 12;

/**
 * Returns true when a header-centered search box of `fieldWidth` would fit in the
 * gap between the left cluster (crumb + workspace chip) and the right actions,
 * i.e. the field can be absolutely centered on the whole header without touching
 * either side. Measured from the field's own slot region, so it responds to the
 * real chip width rather than a fixed breakpoint. Falls back to false (in-flow,
 * centered-in-available) where ResizeObserver is unavailable (jsdom/old webviews).
 */
function useFitsCentered(ref: RefObject<HTMLElement | null>): boolean {
  const [fits, setFits] = useState(false);
  useLayoutEffect(() => {
    const el = ref.current;
    const region = el?.parentElement;
    const header = el?.closest("header");
    if (!el || !region || !header || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      const hw = header.clientWidth;
      const h = header.getBoundingClientRect();
      const r = region.getBoundingClientRect();
      const fieldWidth = Math.min(460, hw * 0.46); // mirrors w-115 / max-w-[46vw]
      const half = fieldWidth / 2 + CENTER_GAP;
      setFits(r.left - h.left <= hw / 2 - half && r.right - h.left >= hw / 2 + half);
    };
    const ro = new ResizeObserver(measure);
    ro.observe(header);
    ro.observe(region);
    measure();
    return () => ro.disconnect();
  }, [ref]);
  return fits;
}

/**
 * The header search field. Styled as an input, acts as a button that opens the
 * palette. It lives in the header's centered region, so by default it centers in
 * the available space between the crumb/workspace chip and the right actions, and
 * can never overlap them (it is a flex sibling). When a true-centered box actually
 * fits the header, it switches to absolute centering so it sits dead-center, which
 * keeps the original look wherever there is room for it.
 */
export function DocsSearchField() {
  const ref = useRef<HTMLButtonElement>(null);
  const centered = useFitsCentered(ref);
  return (
    <button
      ref={ref}
      type="button"
      aria-label="Search the docs"
      onClick={() => window.dispatchEvent(new Event(OPEN_EVENT))}
      className={`flex h-8.5 w-115 max-w-[46vw] items-center gap-2.5 rounded-lg border border-line-2 bg-surface px-3 text-ink-3 shadow-card transition-colors hover:border-line-3 ${
        centered ? "absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2" : ""
      }`}
    >
      <Search size={15} />
      <span className="flex-1 text-left text-body">Search the docs</span>
      <span className="rounded-md border border-line-2 bg-surface-2 px-1.5 py-0.5 font-mono text-micro text-ink-2">
        ⌘K
      </span>
    </button>
  );
}
