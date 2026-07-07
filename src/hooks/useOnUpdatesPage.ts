/**
 * useOnUpdatesPage — true when the Settings → Updates page is open. On that page
 * the row is the single update surface, so the global header pill and the
 * companion toast suppress themselves (context-aware, no stacked duplicates).
 */
import { useLocation } from "react-router-dom";

export function useOnUpdatesPage(): boolean {
  return useLocation().pathname.includes("/settings/updates");
}
