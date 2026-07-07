import { Outlet } from "react-router-dom";
import AppHeader from "./AppHeader";
import ErrorBoundary from "./ErrorBoundary";
import UpdateCompanion from "./UpdateCompanion";
import WhatsNewModal from "./WhatsNewModal";
import WorkspaceSessions from "./WorkspaceSessions";
import { AppConfigProvider } from "../state/appConfig";
import { UpdaterProvider } from "../state/updater";
import { HeaderSlotProvider } from "../state/headerSlot";
import { WorkspaceSessionsProvider } from "../state/workspaceSessions";
import { useEngineLifecycle } from "../hooks/useEngineLifecycle";
import { useDeepLinks } from "../hooks/useDeepLinks";

/**
 * AppLayout — the persistent app shell + root layout route. Owns the global
 * providers, the engine open/close lifecycle (tied to route transitions), the
 * one-shot WhatsNew modal, and the routed `<Outlet/>`.
 *
 * It never unmounts across navigation, so anything it holds (providers, the
 * lifecycle ref) stays stable while pages swap in the outlet. AppHeader renders
 * once here; pages publish their chrome into it via the header-slot system.
 */
export default function AppLayout() {
  useEngineLifecycle();
  useDeepLinks();
  return (
    <AppConfigProvider>
      <UpdaterProvider>
        <HeaderSlotProvider>
          <WorkspaceSessionsProvider>
            {/* Full-bleed window: persistent header, then the routed page fills the rest. */}
            <div className="flex h-screen w-screen flex-col overflow-hidden bg-surface">
              <AppHeader />
              {/* `relative z-0` keeps page panes below the header's stacking context so
                  header dropdowns overlay them. */}
              <div className="relative z-0 flex min-h-0 flex-1 overflow-hidden">
                <ErrorBoundary>
                  {/* Persistent editor sessions: every open workspace stays mounted
                      (terminals alive); only the focused one is visible. The Outlet's
                      editor route renders null and just focuses the matching session. */}
                  <WorkspaceSessions />
                  <Outlet />
                </ErrorBoundary>
              </div>
            </div>
            <WhatsNewModal />
            <UpdateCompanion />
          </WorkspaceSessionsProvider>
        </HeaderSlotProvider>
      </UpdaterProvider>
    </AppConfigProvider>
  );
}
