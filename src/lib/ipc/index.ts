/**
 * Transient barrel: re-exports every `src/lib/ipc/*` domain module so existing
 * `@/lib/ipc` / `../lib/ipc` imports keep resolving unchanged after the
 * monolithic `ipc.ts` was split up. Call sites should migrate to importing
 * directly from the domain module they need; this barrel is scaffolding for
 * that migration, not a permanent home for new exports.
 */
export * from "./core";
export * from "./pty";
export * from "./workspace";
export * from "./engine";
export * from "./history";
export * from "./status";
export * from "./config";
export * from "./fabrication";
export * from "./references";
