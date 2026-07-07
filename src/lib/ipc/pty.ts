/**
 * Typed wrappers over the Rust PTY host commands (see `src-tauri/src/pty.rs`).
 *
 * The Rust commands declare snake_case params (`on_data`, `rows`, `cols`, `data`).
 * Tauri v2 maps JS camelCase arg keys to Rust snake_case params automatically,
 * so we pass `onData` here and Tauri delivers it to the `on_data: Channel<Vec<u8>>`
 * parameter. The other params are already single-word, so the key is identical.
 *
 * Output is streamed over a Tauri **Channel** (not events). The Rust side sends
 * `Vec<u8>`; on the JS side that arrives as a `number[]`, which we convert to a
 * `Uint8Array` before handing it to xterm.
 */
import { Channel } from "@tauri-apps/api/core";
import { invoke } from "./core";

/** Options accepted by {@link ptySpawn}. */
export interface PtySpawnOptions {
  /** Working directory for the shell. Defaults (Rust-side) to $HOME. */
  cwd?: string;
  env?: Record<string, string>;
}

/**
 * Spawn the shell inside a real PTY and stream its raw output to `onData`.
 *
 * @param wsId   Workspace root path — keys the per-workspace PTY session.
 * @param onData Receives every chunk of terminal output as raw bytes.
 * @param opts   Optional working directory / environment overrides.
 */
export async function ptySpawn(
  wsId: string,
  onData: (bytes: Uint8Array) => void,
  opts: PtySpawnOptions = {},
): Promise<void> {
  // `Channel<number[]>` matches the Rust `Channel<Vec<u8>>` payload shape.
  const channel = new Channel<number[]>();
  channel.onmessage = (nums) => onData(Uint8Array.from(nums));

  await invoke("pty_spawn", {
    wsId,
    // camelCase `onData` -> Rust `on_data` (Tauri v2 default arg mapping).
    onData: channel,
    cwd: opts.cwd ?? null,
    env: opts.env ?? null,
  });
}

/** Write raw bytes (keystrokes) to the PTY. */
export async function ptyWrite(wsId: string, data: Uint8Array): Promise<void> {
  // Tauri serializes `Uint8Array` directly to a Rust `Vec<u8>` for the `data` param.
  await invoke("pty_write", { wsId, data });
}

/** Resize the PTY to the given terminal dimensions. */
export async function ptyResize(wsId: string, rows: number, cols: number): Promise<void> {
  await invoke("pty_resize", { wsId, rows, cols });
}
