import { useEffect, useState } from "react";

/**
 * Track the heading id currently in view for the "On this page" rail. Observes
 * the given ids and reports the topmost one intersecting the upper viewport.
 * Falls back to the first id where IntersectionObserver is unavailable (jsdom,
 * older webviews), so callers can render the rail without a guard.
 */
export function useActiveHeading(ids: string[]): string | null {
  const [active, setActive] = useState<string | null>(ids[0] ?? null);
  const key = ids.join("|");
  useEffect(() => {
    if (ids.length === 0) return;
    if (typeof IntersectionObserver === "undefined") return;
    const seen = new Map<string, boolean>();
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) seen.set(e.target.id, e.isIntersecting);
        const first = ids.find((id) => seen.get(id));
        if (first) setActive(first);
      },
      { rootMargin: "0px 0px -70% 0px", threshold: 0 },
    );
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) obs.observe(el);
    }
    return () => obs.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return active;
}
