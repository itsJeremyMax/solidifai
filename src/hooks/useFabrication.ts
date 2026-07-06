/**
 * useFabrication — imperative fabrication actions for the current build.
 *
 * Unlike the read-only analysis hooks, most actions here run on demand (the
 * user clicks a button), so the hook exposes action callbacks rather than an
 * auto-fetch effect. `list` and `save` manage the destination list, which is
 * typically fetched once when the Fab panel opens.
 */
import { useCallback, useEffect, useState } from "react";

import {
  engineFabDetect,
  engineFabEstimate,
  engineFabOpen,
  engineFabOrient,
  getDestinations,
  getSlicerProfiles,
  setDestinations as writeDestinations,
} from "../lib/ipc";
import {
  parseEstimate,
  parseInstallInfo,
  parseOrientResult,
  type Destination,
  type Estimate,
  type InstallInfo,
  type OrientResult,
  type ProfileSet,
} from "../lib/fabrication";

export interface FabricationState {
  install: InstallInfo | null;
  profiles: ProfileSet | null;
  estimate: Estimate | null;
  orient: OrientResult | null;
  destinations: Destination[];
  loading: boolean;
  error: string | null;
  /** Detect the installed slicer. */
  detect: () => Promise<void>;
  /** Load available printer + filament profiles. */
  fetchProfiles: () => Promise<void>;
  /** Estimate print time / filament for an optional destination. */
  fetchEstimate: (destinationId?: string | null) => Promise<void>;
  /** Suggest the best print orientation. */
  findOrientation: () => Promise<void>;
  /** Open / slice the model at an optional destination. */
  open: (destinationId?: string | null) => Promise<void>;
  /** Refresh the destination list from the engine. */
  list: () => Promise<void>;
  /** Persist a new destination list. */
  save: (destinations: Destination[]) => Promise<void>;
}

export function useFabrication(buildId: number): FabricationState {
  const [install, setInstall] = useState<InstallInfo | null>(null);
  const [profiles, setProfiles] = useState<ProfileSet | null>(null);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [orient, setOrient] = useState<OrientResult | null>(null);
  const [destinations, setDestinations] = useState<Destination[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Estimate + orient results are tied to the current geometry; clear them when
  // the build changes so stale numbers aren't shown after a rebuild.
  useEffect(() => {
    setEstimate(null);
    setOrient(null);
    setError(null);
  }, [buildId]);

  const detect = useCallback(async () => {
    setLoading(true);
    setError(null);
    const raw = await engineFabDetect();
    const parsed = raw ? parseInstallInfo(raw) : null;
    if (parsed) setInstall(parsed);
    else setError("Could not detect a slicer installation.");
    setLoading(false);
  }, []);

  const fetchProfiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setProfiles(await getSlicerProfiles());
    } catch {
      setError("Could not load slicer profiles.");
    }
    setLoading(false);
  }, []);

  const fetchEstimate = useCallback(async (destinationId?: string | null) => {
    setLoading(true);
    setError(null);
    const raw = await engineFabEstimate(destinationId);
    if (raw) {
      try {
        const envelope = JSON.parse(raw) as Record<string, unknown>;
        if (envelope.ok === false) {
          // Engine has no model loaded or estimation failed.
          const msg =
            typeof envelope.error === "string"
              ? envelope.error
              : "No model loaded. Build one first.";
          setError(msg);
          setLoading(false);
          return;
        }
      } catch {
        // Fall through to parseEstimate which handles bad JSON.
      }
    }
    const parsed = raw ? parseEstimate(raw) : null;
    if (parsed) setEstimate(parsed);
    else setError("Could not estimate print time.");
    setLoading(false);
  }, []);

  const findOrientation = useCallback(async () => {
    setLoading(true);
    setError(null);
    const raw = await engineFabOrient();
    const parsed = raw ? parseOrientResult(raw) : null;
    if (parsed) setOrient(parsed);
    else setError("Could not compute print orientation.");
    setLoading(false);
  }, []);

  const open = useCallback(async (destinationId?: string | null) => {
    setLoading(true);
    setError(null);
    const raw = await engineFabOpen(destinationId);
    if (!raw) setError("Could not open the model for printing.");
    setLoading(false);
  }, []);

  const list = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDestinations(await getDestinations());
    } catch {
      setDestinations([]);
    }
    setLoading(false);
  }, []);

  const save = useCallback(async (next: Destination[]) => {
    setLoading(true);
    setError(null);
    try {
      setDestinations(await writeDestinations(next));
    } catch {
      setError("Could not save destinations.");
    }
    setLoading(false);
  }, []);

  return {
    install,
    profiles,
    estimate,
    orient,
    destinations,
    loading,
    error,
    detect,
    fetchProfiles,
    fetchEstimate,
    findOrientation,
    open,
    list,
    save,
  };
}
