/* eslint-disable react-refresh/only-export-components -- route-config module: the
   router object is exported alongside its route wrapper components by design. */
import { useEffect } from "react";
import { createHashRouter, Navigate, useNavigate, useParams } from "react-router-dom";

import AppLayout from "./components/AppLayout";
import HomeView from "./components/home/HomeView";
import SettingsLayout from "./components/SettingsLayout";
import MaterialsView from "./components/materials/MaterialsView";
import MaterialDrawerRoute from "./components/materials/MaterialDrawerRoute";
import FactoryView from "./components/factory/FactoryView";
import ConnectionEditor from "./components/factory/ConnectionEditor";
import ReferencesView from "./components/references/ReferencesView";
import ReferenceEditor from "./components/references/ReferenceEditor";
import DocsLayout from "./components/docs/DocsLayout";
import DocPage from "./components/docs/DocPage";
import HelpView from "./components/help/HelpView";
import { SETTINGS_SECTIONS, SETTINGS_SECTION_IDS } from "./components/settings/sections";
import { decodeWsPath, editorPath } from "./lib/routes";
import { DOC_SLUGS } from "./lib/docs";
import { useWorkspaceSessions } from "./state/workspaceSessions";
import { basename, type Workspace } from "./lib/workspaces";

/** Material editor drawer sub-routes (new + edit), reused at every materials mount. */
function materialsChildren() {
  return [
    { path: "new", element: <MaterialDrawerRoute /> },
    { path: ":materialId", element: <MaterialDrawerRoute /> },
  ];
}

/** Connection editor sub-routes (new + edit), reused at every factory mount. */
function factoryChildren() {
  return [
    { path: "new", element: <ConnectionEditor /> },
    { path: ":connectionId", element: <ConnectionEditor /> },
  ];
}

/** Reference editor sub-routes (new + edit), reused at every references mount. */
function referencesChildren() {
  return [
    { path: "new", element: <ReferenceEditor /> },
    { path: ":entryId", element: <ReferenceEditor /> },
  ];
}

/** Settings sub-routes generated from the registry: an index redirect to the
 *  first section, then one route per section. Reused at every settings mount. */
function settingsChildren() {
  return [
    { index: true, element: <Navigate to={SETTINGS_SECTION_IDS[0]} replace /> },
    ...SETTINGS_SECTIONS.map((s) => ({ path: s.id, element: s.element })),
  ];
}

/** Docs sub-routes: an index redirect to the first page, then one route per
 *  page slug. The slug list comes from the docs registry, so adding a markdown
 *  file to docs/guide adds its route with no change here. */
function docsChildren() {
  return [
    { index: true, element: <Navigate to={DOC_SLUGS[0] ?? ""} replace /> },
    { path: ":slug", element: <DocPage /> },
  ];
}

/**
 * Route table for the whole app. Thin wrapper components adapt the existing view
 * components by fulfilling their callback props via `navigate()`. The engine
 * open/close is handled centrally by `useEngineLifecycle` in {@link AppLayout},
 * so wrappers only navigate. "Back" is browser history (`navigate(-1)`).
 */

function LauncherRoute() {
  const navigate = useNavigate();
  return (
    <HomeView
      onEnterWorkspace={(ws: Workspace) => navigate(editorPath(ws.path))}
      onOpenSettings={() => navigate("/settings")}
      onOpenMaterials={() => navigate("/materials")}
      onOpenFactory={() => navigate("/factory")}
      onOpenReferences={() => navigate("/references")}
    />
  );
}

function EditorRoute() {
  const { wsPath = "" } = useParams();
  const path = decodeWsPath(wsPath);
  const { focus } = useWorkspaceSessions();
  // The session's AppShell is mounted by the persistent WorkspaceSessions layer;
  // this route just focuses the matching session (opening it if it's not yet open).
  useEffect(() => {
    focus(path);
  }, [path, focus]);
  return null;
}

function MaterialsRoute({ scope }: { scope: "global" | "workspace" }) {
  const { wsPath } = useParams();
  // Workspace scope derives its name from the route; global scope has none.
  const workspaceName =
    scope === "workspace" && wsPath ? basename(decodeWsPath(wsPath)) || null : null;
  return <MaterialsView scope={scope} workspaceName={workspaceName} />;
}

export const router = createHashRouter([
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <LauncherRoute /> },
      { path: "/settings", element: <SettingsLayout />, children: settingsChildren() },
      {
        path: "/materials",
        element: <MaterialsRoute scope="global" />,
        children: materialsChildren(),
      },
      { path: "/factory", element: <FactoryView />, children: factoryChildren() },
      {
        path: "/references",
        element: <ReferencesView />,
        children: referencesChildren(),
      },
      { path: "/docs", element: <DocsLayout />, children: docsChildren() },
      { path: "/help", element: <HelpView /> },
      {
        path: "/w/:wsPath",
        children: [
          { index: true, element: <EditorRoute /> },
          { path: "settings", element: <SettingsLayout />, children: settingsChildren() },
          {
            path: "materials",
            element: <MaterialsRoute scope="workspace" />,
            children: materialsChildren(),
          },
          { path: "factory", element: <FactoryView />, children: factoryChildren() },
          {
            path: "references",
            element: <ReferencesView />,
            children: referencesChildren(),
          },
        ],
      },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
