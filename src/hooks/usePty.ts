/**
 * usePty — mounts an `@xterm/xterm` terminal into a container and wires it to the
 * Rust PTY host:
 *
 *   PTY output (Channel<Vec<u8>>) ──▶ term.write(bytes)
 *   term.onData (keystrokes)       ──▶ ptyWrite(bytes)
 *   fit / container resize         ──▶ ptyResize(rows, cols)
 *
 * The terminal and PTY are created on mount and disposed on unmount. A `disposed`
 * flag guards the async spawn against StrictMode's setup → cleanup → setup in dev.
 *
 * The session is keyed by `wsPath` — the workspace root, which is BOTH the PTY
 * session id and the shell's cwd (model.json/.glb + .mcp.json live there). A
 * `wsPath` change tears down + respawns this terminal (it's a different session);
 * a background session keeps its shell alive as long as it stays mounted.
 *
 * `opts.note` — if set, a dimmed one-liner printed after spawn succeeds (used to
 * communicate "session restored" on relaunch). Captured via ref so a changed note
 * string never re-runs the spawn effect.
 */
import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";

import { ptyResize, ptySpawn, ptyWrite } from "../lib/ipc";

/** xterm theme tuned to the solidifai dark `term` surface + cobalt accent. */
const TERM_THEME = {
  background: "#14161C",
  foreground: "#C9D1DC",
  cursor: "#2B6CFF",
  cursorAccent: "#14161C",
  selectionBackground: "rgba(43,108,255,0.22)",
  selectionInactiveBackground: "rgba(201,209,220,0.12)",
  black: "#14161C",
  red: "#E5707B",
  green: "#52DA8B",
  yellow: "#E8C97A",
  blue: "#74A6FF",
  magenta: "#B79CFF",
  cyan: "#6FD4D0",
  white: "#C9D1DC",
  brightBlack: "#6A7180",
  brightRed: "#F08A93",
  brightGreen: "#74E6A2",
  brightYellow: "#F2D98F",
  brightBlue: "#9CC0FF",
  brightMagenta: "#CBB6FF",
  brightCyan: "#92E3DF",
  brightWhite: "#EAEDF2",
} as const;

const encoder = new TextEncoder();

export interface UsePtyOpts {
  /** Optional dimmed note printed once after the shell spawns. */
  note?: string;
  /** Whether this terminal's tab is currently visible. When it transitions to
   *  true, force a re-fit + full repaint so the buffer is clean after display:none. */
  visible?: boolean;
}

export function usePty(
  containerRef: React.RefObject<HTMLDivElement | null>,
  wsPath: string,
  opts?: UsePtyOpts,
) {
  // Keep note in a ref so changing it never re-triggers the spawn effect.
  const noteRef = useRef(opts?.note);
  noteRef.current = opts?.note;

  // Stable refs to term + fit so the visibility effect can reach them without
  // being a dependency of the mount effect or vice versa.
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const term = new Terminal({
      fontFamily: '"IBM Plex Mono", ui-monospace, monospace',
      fontSize: 12,
      lineHeight: 1.6,
      cursorBlink: true,
      cursorStyle: "bar",
      allowProposedApi: true,
      theme: { ...TERM_THEME },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(container);

    termRef.current = term;
    fitRef.current = fit;

    // Set in cleanup; guards every async tail below from touching a disposed term.
    let disposed = false;
    const dataDisp = term.onData((data) => {
      void ptyWrite(wsPath, encoder.encode(data));
    });
    const resizeDisp = term.onResize(({ rows, cols }) => {
      void ptyResize(wsPath, rows, cols);
    });

    // fit() calls term.resize() internally, which fires the term.onResize handler
    // (wired to ptyResize above) only when the dimensions actually change. So no
    // explicit ptyResize call here: switching to a same-size hidden terminal no
    // longer sends a spurious resize → SIGWINCH → prompt redraw/duplication.
    const fitAndResize = () => {
      try {
        fit.fit();
      } catch {
        // No layout yet (display:none); fit() throws — skip silently.
      }
    };

    const observer = new ResizeObserver(() => fitAndResize());
    observer.observe(container);
    fitAndResize();
    term.focus();

    // Spawn the shell in the workspace root (its model.json/.glb + .mcp.json live
    // there) keyed by that same path. pty_spawn reaps any prior shell for this wsId.
    void ptySpawn(
      wsPath,
      (bytes) => {
        if (!disposed) term.write(bytes);
      },
      { cwd: wsPath },
    )
      .then(() => {
        if (!disposed) {
          void ptyResize(wsPath, term.rows, term.cols);
          const note = noteRef.current;
          if (note) term.writeln("\x1b[2m" + note + "\x1b[0m");
        }
      })
      .catch((e) => {
        if (!disposed) term.writeln(`\r\n\x1b[31m[pty error]\x1b[0m ${String(e)}`);
      });

    return () => {
      disposed = true;
      observer.disconnect();
      dataDisp.dispose();
      resizeDisp.dispose();
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
    };
    // A wsPath change tears this terminal down + respawns it (a different session).
  }, [containerRef, wsPath]);

  // When the tab becomes visible, re-fit and force a full repaint of the buffer.
  // xterm's renderer doesn't paint while display:none, so on show the previous
  // frame can be stale (duplicate rows). fit() only sends ptyResize when the size
  // actually changed, so a same-size show won't SIGWINCH the shell.
  useEffect(() => {
    if (!opts?.visible) return;
    const term = termRef.current;
    const fit = fitRef.current;
    if (!term || !fit) return;
    const id = requestAnimationFrame(() => {
      try {
        fit.fit();
      } catch {
        return;
      }
      term.refresh(0, term.rows - 1);
      term.scrollToBottom();
    });
    return () => cancelAnimationFrame(id);
  }, [opts?.visible]);
}
