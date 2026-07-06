// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router-dom";
import { useRouteRestore } from "./useRouteRestore";
import { saveLastRoute } from "../lib/lastRoute";

const listWorkspaces = vi.fn();
vi.mock("../lib/workspaces", () => ({ listWorkspaces: () => listWorkspaces() }));

function Layout() {
  useRouteRestore();
  return <Outlet />;
}

function makeRouter() {
  return createMemoryRouter(
    [
      {
        element: <Layout />,
        children: [
          { path: "/", element: <div>home</div> },
          { path: "/settings/about", element: <div>about</div> },
          { path: "/w/:wsPath", element: <div>editor</div> },
        ],
      },
    ],
    { initialEntries: ["/"] },
  );
}

// Node's experimental global localStorage shadows jsdom's; install an in-memory one.
const store = new Map<string, string>();
beforeEach(() => {
  store.clear();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => {
      store.set(k, v);
    },
    removeItem: (k: string) => {
      store.delete(k);
    },
    clear: () => store.clear(),
  });
  listWorkspaces.mockReset();
});
afterEach(cleanup);

describe("useRouteRestore", () => {
  it("restores a saved non-editor route on launch", async () => {
    saveLastRoute("/settings/about");
    render(<RouterProvider router={makeRouter()} />);
    expect(await screen.findByText("about")).toBeTruthy();
  });

  it("restores a saved editor route whose workspace still exists", async () => {
    const p = "/here";
    saveLastRoute("/w/" + encodeURIComponent(p));
    listWorkspaces.mockResolvedValue([{ name: "here", path: p }]);
    render(<RouterProvider router={makeRouter()} />);
    expect(await screen.findByText("editor")).toBeTruthy();
  });

  it("drops a saved editor route whose workspace is gone", async () => {
    saveLastRoute("/w/" + encodeURIComponent("/gone"));
    listWorkspaces.mockResolvedValue([]);
    render(<RouterProvider router={makeRouter()} />);
    expect(await screen.findByText("home")).toBeTruthy();
  });
});
