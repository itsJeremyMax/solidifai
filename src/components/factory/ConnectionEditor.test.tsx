// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router-dom";
import type { Destination } from "../../lib/fabrication";
import type { FactoryOutletContext } from "./factoryContext";
import ConnectionEditor from "./ConnectionEditor";

afterEach(cleanup);

const garage: Destination = { id: "g1", name: "Garage printer", kind: "local", provider: "orca" };

function ctx(): FactoryOutletContext {
  return {
    destinations: [garage],
    profiles: { found: true, printers: [], filaments: [], processes: [] },
    fetchProfiles: vi.fn().mockResolvedValue(undefined),
    save: vi.fn().mockResolvedValue(undefined),
  };
}

function mount(initial: string, entries: string[] = [initial]) {
  const r = createMemoryRouter(
    [
      {
        path: "/factory",
        element: <Outlet context={ctx()} />,
        children: [
          { path: "new", element: <ConnectionEditor /> },
          { path: ":connectionId", element: <ConnectionEditor /> },
        ],
      },
    ],
    { initialEntries: entries, initialIndex: entries.length - 1 },
  );
  return render(<RouterProvider router={r} />);
}

describe("ConnectionEditor", () => {
  it("shows a blank new-connection form on the new route", async () => {
    mount("/factory/new");
    expect(await screen.findByText("New connection")).toBeTruthy();
    expect((screen.getByPlaceholderText("Garage printer") as HTMLInputElement).value).toBe("");
  });

  it("prefills the existing connection on the :connectionId route", async () => {
    mount("/factory/g1");
    expect(await screen.findByText("Edit connection")).toBeTruthy();
    expect((screen.getByPlaceholderText("Garage printer") as HTMLInputElement).value).toBe(
      "Garage printer",
    );
  });

  // Closing must always dismiss the modal — popping real history when present
  // (so a later Back doesn't reopen it), else falling back to the parent route.
  it("closes the modal when Cancel is clicked (pops history)", async () => {
    mount("/factory/new", ["/factory", "/factory/new"]);
    expect(await screen.findByText("New connection")).toBeTruthy();
    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("closes the modal when the X is clicked", async () => {
    mount("/factory/new", ["/factory", "/factory/new"]);
    expect(await screen.findByText("New connection")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Close"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("closes on a direct load with no history to pop", async () => {
    mount("/factory/new"); // single entry: location.key === "default"
    expect(await screen.findByText("New connection")).toBeTruthy();
    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("requires confirmation before removing a connection", async () => {
    mount("/factory/g1", ["/factory", "/factory/g1"]);
    await screen.findByText("Edit connection");
    fireEvent.click(screen.getByText("Remove"));
    // The confirm step replaces the form (no immediate delete).
    expect(await screen.findByText("Remove connection")).toBeTruthy();
    expect(screen.getByText(/cannot be undone/i)).toBeTruthy();
    expect(screen.queryByText("Edit connection")).toBeNull();
    // Backing out returns to the form.
    fireEvent.click(screen.getByText("Cancel"));
    expect(await screen.findByText("Edit connection")).toBeTruthy();
  });

  it("removes the connection only after the confirm step", async () => {
    mount("/factory/g1", ["/factory", "/factory/g1"]);
    await screen.findByText("Edit connection");
    fireEvent.click(screen.getByText("Remove"));
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("blocks a duplicate connection name (case-insensitive)", async () => {
    mount("/factory/new");
    await screen.findByText("New connection");
    fireEvent.change(screen.getByPlaceholderText("Garage printer"), {
      target: { value: "garage PRINTER" }, // collides with existing "Garage printer"
    });
    expect(await screen.findByText(/already exists/i)).toBeTruthy();
    expect(
      (screen.getByText("Add connection").closest("button") as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("disables the profile dropdowns when there are no profiles", async () => {
    mount("/factory/new"); // fixture profiles: found but empty lists
    await screen.findByText("New connection");
    expect((screen.getByLabelText("Printer profile") as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByLabelText("Filament profile") as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByLabelText("Process profile") as HTMLSelectElement).disabled).toBe(true);
  });
});
