import type { Destination, ProfileSet } from "../../lib/fabrication";

/**
 * Data the Factory grid shares with its editor route (`new` / `:connectionId`)
 * via Outlet context. The grid owns the connection list (one app-level store);
 * the editor owns only the in-progress form and persists whole-list changes back
 * through `save`.
 */
export interface FactoryOutletContext {
  destinations: Destination[];
  profiles: ProfileSet | null;
  fetchProfiles: () => Promise<void>;
  save: (destinations: Destination[]) => Promise<void>;
}
