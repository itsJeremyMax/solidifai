/**
 * Route helpers. A workspace has no stable id — its identity is its absolute
 * path — so the editor route param is the path encoded into a single URL segment
 * (slashes escaped). These keep that encode/decode in one place.
 */

/** Encode an absolute workspace path into a single URL segment (slashes escaped). */
export function encodeWsPath(path: string): string {
  return encodeURIComponent(path);
}

/** Inverse of {@link encodeWsPath}. */
export function decodeWsPath(seg: string): string {
  return decodeURIComponent(seg);
}

/** The editor route for a workspace path. */
export function editorPath(path: string): string {
  return `/w/${encodeWsPath(path)}`;
}
