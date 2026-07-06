/**
 * Frontend logging sink. Writes to the devtools console and forwards to the Rust
 * shell log (best-effort) so field failures land in the app log file alongside
 * shell + engine logs. Routing every caller through this one function keeps that
 * forwarding a single edit rather than a sweep of console.* calls.
 */
import { invoke } from "@tauri-apps/api/core";

/** Log a handled error with a short context label and optional structured info. */
export function logError(context: string, error: unknown, info?: Record<string, unknown>): void {
  console.error(`[solidifai] ${context}`, error, info ?? {});

  const message =
    error instanceof Error ? `${context}: ${error.message}` : `${context}: ${String(error)}`;
  const stack =
    (error instanceof Error ? error.stack : undefined) ??
    (typeof info?.componentStack === "string" ? info.componentStack : undefined);
  const source = typeof info?.source === "string" ? info.source : undefined;

  // Best-effort: forwarding must never throw back into the caller. The try/catch
  // covers a synchronous throw (no Tauri IPC, e.g. tests); .catch covers an async
  // rejection. A failed forward stays on the console, never re-forwarded.
  try {
    void invoke("log_frontend_error", { message, source, stack }).catch(() => {});
  } catch {
    /* no Tauri IPC available */
  }
}
