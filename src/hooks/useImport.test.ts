import { describe, expect, it } from "vitest";

import {
  LEGACY_IMPORT_EXTENSIONS,
  isSupportedImport,
  normalizeImportExtensions,
} from "./useImport";
import { firstSupported } from "./useFileDrop";

describe("import capability extensions", () => {
  it("uses SVG consistently for direct imports and drops when advertised", () => {
    const extensions = normalizeImportExtensions('{"formats":{"svg":{"extensions":[".svg"]}}}');

    expect(extensions).toEqual(["svg"]);
    expect(isSupportedImport("/tmp/logo.svg", extensions)).toBe(true);
    expect(firstSupported(["/tmp/logo.svg"], extensions)).toBe("/tmp/logo.svg");
  });

  it("falls back to legacy extensions and rejects unsupported direct imports and drops", () => {
    expect(normalizeImportExtensions(null)).toEqual(LEGACY_IMPORT_EXTENSIONS);
    expect(isSupportedImport("/tmp/logo.svg", LEGACY_IMPORT_EXTENSIONS)).toBe(false);
    expect(firstSupported(["/tmp/logo.svg"], LEGACY_IMPORT_EXTENSIONS)).toBeUndefined();
  });
});
