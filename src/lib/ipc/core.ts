/**
 * Shared foundation for the `src/lib/ipc/` domain modules: the Tauri `invoke`
 * used everywhere, and `engineCall`, which factors out the try/catch-return-null
 * body repeated by ipc.ts's `string | null` engine functions (e.g.
 * `engineSetParams`, `engineRender`, `engineMeasure`, `engineGetParams`).
 */
import { invoke, type InvokeArgs } from "@tauri-apps/api/core";

export { invoke };

/**
 * Invoke an engine RPC and return its raw response, or `null` if the call
 * rejects for any reason (engine not ready, workspace not open, command
 * missing on an older backend, etc). Every existing `string | null` engine
 * function in `ipc.ts` swallows all errors this way rather than checking a
 * specific "not ready" signal, so this helper does the same rather than
 * narrowing to a subset of failures.
 */
export async function engineCall<T>(method: string, args?: InvokeArgs): Promise<T | null> {
  try {
    return await invoke<T>(method, args);
  } catch {
    return null;
  }
}
