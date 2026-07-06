/**
 * GPU render-target readback → canvas-ready pixel packing.
 *
 * Row order depends on the active backend: three's WebGPU copyTextureToBuffer
 * returns rows top-down (row 0 = top, matching a 2D canvas), while the WebGL2
 * fallback's gl.readPixels returns rows bottom-up (origin at the lower-left),
 * so those must be flipped vertically. WebGPU readback rows are also padded to
 * a 256-byte stride; the real stride is derived from the buffer so
 * non-64-aligned widths don't shear (packed buffers reduce to w*4 naturally).
 */

/** True when the renderer runs the WebGL2 fallback backend (readback is bottom-up). */
export function isWebGLReadback(renderer: { backend: unknown }): boolean {
  return (renderer.backend as { isWebGLBackend?: boolean }).isWebGLBackend === true;
}

/**
 * Pack one `w`×`h` RGBA8 readback frame into a tight, top-down pixel array
 * ready for ImageData. `flipY` reverses the row order (WebGL readback).
 */
export function packReadbackRows(
  buf: Uint8Array,
  w: number,
  h: number,
  flipY: boolean,
): Uint8ClampedArray<ArrayBuffer> {
  const dstRowBytes = w * 4;
  const srcRowBytes = Math.floor(buf.length / h); // aligned stride (w*4 when packed)
  const out = new Uint8ClampedArray(dstRowBytes * h);
  for (let y = 0; y < h; y++) {
    const srcStart = y * srcRowBytes;
    const dstStart = (flipY ? h - 1 - y : y) * dstRowBytes;
    out.set(buf.subarray(srcStart, srcStart + dstRowBytes), dstStart);
  }
  return out;
}
