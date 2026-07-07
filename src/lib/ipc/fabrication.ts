import type { Destination, ProfileSet, SlicerEntry } from "../fabrication";
import { engineCall, invoke } from "./core";

/* ───────────────────────────── fabrication ────────────────────────────── */

/** Detect the installed slicer / fabrication tool. Returns raw engine JSON or `null`. */
export async function engineFabDetect(): Promise<string | null> {
  return engineCall<string>("engine_fab_detect");
}

/** Estimate print time / filament for a destination. Returns raw engine JSON or `null`. */
export async function engineFabEstimate(destinationId?: string | null): Promise<string | null> {
  return engineCall<string>("engine_fab_estimate", { destinationId: destinationId ?? null });
}

/**
 * Suggest the best print orientation to minimise overhangs. Returns raw engine
 * JSON or `null`. Leave `overhangDeg` unset to use the workspace's manufacturing
 * profile (process.overhangDeg), so this matches what Sol's fab_orient does.
 */
export async function engineFabOrient(overhangDeg?: number): Promise<string | null> {
  try {
    const args = overhangDeg === undefined ? {} : { overhangDeg };
    return await invoke<string>("engine_fab_orient", args);
  } catch {
    return null;
  }
}

/** Open (slice / send) the model to a fabrication destination. Returns raw engine JSON or `null`. */
export async function engineFabOpen(destinationId?: string | null): Promise<string | null> {
  return engineCall<string>("engine_fab_open", { destinationId: destinationId ?? null });
}

/**
 * App-level fabrication data is served natively (not via the workspace engine),
 * so the Factory page works without a workspace open. These mirror the materials
 * commands: they throw on failure and the caller decides how to surface it.
 */

/** Configured print destinations (connections) from the app config store. */
export async function getDestinations(): Promise<Destination[]> {
  return await invoke<Destination[]>("get_destinations");
}

/** Persist the destination list; returns the reloaded authoritative copy. */
export async function setDestinations(destinations: Destination[]): Promise<Destination[]> {
  return await invoke<Destination[]>("set_destinations", { destinations });
}

/** Printer + filament profile names discovered from the installed slicer. */
export async function getSlicerProfiles(): Promise<ProfileSet> {
  return await invoke<ProfileSet>("get_slicer_profiles");
}

/** Supported slicers with detection status + override, for Settings → Slicers. */
export async function getSlicerConfig(): Promise<SlicerEntry[]> {
  return await invoke<SlicerEntry[]>("get_slicer_config");
}

/** Set (or clear, with `null`) a slicer's binary override; returns refreshed config. */
export async function setSlicerOverride(
  id: string,
  executablePath: string | null,
): Promise<SlicerEntry[]> {
  return await invoke<SlicerEntry[]>("set_slicer_override", {
    id,
    executablePath,
  });
}

/** Native picker for a slicer executable (a macOS `.app` is accepted). */
export async function pickSlicerBinary(): Promise<string | null> {
  return (await invoke<string | null>("pick_slicer_binary")) ?? null;
}
