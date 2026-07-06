import { useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";

/**
 * A "go back" handler that pops real in-app history when there is some, and
 * otherwise navigates to `fallback`. Use it for header Back buttons and for
 * closing route-modals: closing via `navigate("..")` PUSHES a duplicate parent
 * entry, so a later Back lands back inside the modal. Popping (`navigate(-1)`)
 * keeps an open/close pair history-neutral; the `fallback` covers a direct load
 * or restored deep link, where there is nothing to pop.
 */
export function useGoBack(fallback: string, opts?: { replace?: boolean }): () => void {
  const navigate = useNavigate();
  const { key } = useLocation();
  const replace = opts?.replace ?? false;
  return useCallback(() => {
    // The router's initial entry has key "default"; any in-app navigation gets a
    // unique key, so a non-default key means there is history to pop.
    if (key !== "default") navigate(-1);
    else navigate(fallback, { replace });
  }, [navigate, key, fallback, replace]);
}
