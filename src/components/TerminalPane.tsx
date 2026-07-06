/**
 * TerminalPane — live `@xterm/xterm` terminal wired to the Rust PTY host.
 *
 * Keeps the dark `bg-term` panel chrome from the original static placeholder
 * (radius 10, IBM Plex Mono, inset highlight + soft drop shadow, faint cobalt
 * corner wash). The static markup is replaced by an xterm mount point driven by
 * the `usePty` hook, which spawns the shell and streams I/O over a Tauri Channel.
 */
import "@xterm/xterm/css/xterm.css";
import { useRef } from "react";

import { usePty } from "../hooks/usePty";
import { useWorkspaceSessions } from "../state/workspaceSessions";

export default function TerminalPane({ wsPath, active }: { wsPath: string; active: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { wasRestored } = useWorkspaceSessions();

  const note = wasRestored(wsPath)
    ? "session restored. the previous agent run did not carry over."
    : undefined;

  usePty(containerRef, wsPath, { note, visible: active });

  return (
    <div className="relative m-3 mt-0 flex-1 overflow-hidden rounded-xl bg-term px-3.75 pb-3.25 pt-3.75 font-mono text-xs leading-[1.6] text-term-ink shadow-[inset_0_1px_0_rgba(255,255,255,.04),0_1px_2px_rgba(16,18,24,.05),0_14px_30px_-14px_rgba(16,18,24,.18)]">
      {/* faint cobalt corner wash — sits above the terminal's solid bg */}
      <div className="pointer-events-none absolute inset-0 z-[1]" />

      <div ref={containerRef} className="relative z-[2] h-full w-full" />
    </div>
  );
}
