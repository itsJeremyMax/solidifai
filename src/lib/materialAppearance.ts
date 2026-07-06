import type { Material } from "./materials";

/** Base substance PBR baseline (mirror of engine BUILTIN metalness; density not needed here). */
const BASE_METALNESS: Record<string, number> = {
  pla: 0,
  abs: 0,
  petg: 0,
  nylon: 0,
  aluminum: 1,
  steel: 1,
  stainless: 1,
  brass: 1,
  copper: 1,
};

/** Finish presets: MUST match engine `FINISH_PRESETS`. */
const FINISH: Record<
  string,
  { roughness: number; clearcoat: number; clearcoatRoughness: number; forceMetal: boolean }
> = {
  matte: { roughness: 0.85, clearcoat: 0.0, clearcoatRoughness: 0.0, forceMetal: false },
  satin: { roughness: 0.55, clearcoat: 0.1, clearcoatRoughness: 0.3, forceMetal: false },
  gloss: { roughness: 0.25, clearcoat: 0.6, clearcoatRoughness: 0.2, forceMetal: false },
  metallic: { roughness: 0.35, clearcoat: 0.0, clearcoatRoughness: 0.0, forceMetal: true },
};

function srgbToLinear(c: number): number {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

export function hexToLinear(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const ch = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  return ch.map(srgbToLinear) as [number, number, number];
}

export interface PbrAppearance {
  baseColor: [number, number, number]; // linear RGB
  metalness: number;
  roughness: number;
  clearcoat: number;
  clearcoatRoughness: number;
}

export function appearanceFor(m: Pick<Material, "base" | "colorHex" | "finish">): PbrAppearance {
  const f = FINISH[m.finish] ?? FINISH.matte;
  const metalness = f.forceMetal ? 1 : (BASE_METALNESS[m.base] ?? 0);
  return {
    baseColor: hexToLinear(m.colorHex),
    metalness,
    roughness: f.roughness,
    clearcoat: f.clearcoat,
    clearcoatRoughness: f.clearcoatRoughness,
  };
}

/** Stable key for the thumbnail cache: only the inputs that change the render. */
export function appearanceHash(m: Pick<Material, "base" | "colorHex" | "finish">): string {
  return `${m.base}|${m.colorHex.toLowerCase()}|${m.finish}`;
}
