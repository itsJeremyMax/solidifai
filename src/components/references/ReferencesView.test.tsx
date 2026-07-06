// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";

// Open-in-OS is the only Tauri surface a row touches; stub it so a click is inert.
const openUrl = vi.fn();
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: (u: string) => openUrl(u) }));

// The page owns no data fetching; it reads everything from the hook, which we mock.
const save = vi.fn();
const remove = vi.fn();
let entries: import("../../hooks/useReferences").ReferenceRow[] = [];
vi.mock("../../hooks/useReferences", () => ({
  useReferences: () => ({ entries, error: null, save, remove, reload: vi.fn() }),
}));

import { HeaderSlotProvider } from "../../state/headerSlot";
import ReferencesView from "./ReferencesView";
import type { ReferenceRow } from "../../hooks/useReferences";

const usbc: ReferenceRow = {
  id: "usb-c",
  category: "connector",
  dims_mm: { receptacle: [8.94, 3.16], height: 3.16 },
  source: "https://usb.org/usb-c",
  builtin: true,
  shadowsSeed: false,
};

const pi: ReferenceRow = {
  id: "raspberry-pi-5",
  category: "sbc",
  dims_mm: { pcb: [85, 56, 1.4], height_max: 18 },
  source: "https://raspberrypi.com/pi5",
  aliases: ["rpi5", "pi 5"],
  origin: "learned",
  verified_in: "cyberdeck",
  verified_at: "2026-06-11T10:00:00Z",
  builtin: false,
  shadowsSeed: false,
};

function renderPage() {
  return render(
    <HeaderSlotProvider>
      <MemoryRouter initialEntries={["/references"]}>
        <Routes>
          <Route path="/references" element={<ReferencesView />} />
        </Routes>
      </MemoryRouter>
    </HeaderSlotProvider>,
  );
}

describe("ReferencesView", () => {
  beforeEach(() => {
    entries = [pi, usbc];
    openUrl.mockReset();
    save.mockReset();
    remove.mockReset();
  });
  afterEach(cleanup);

  it("renders a builtin and a learned row with id, category, and dims", () => {
    renderPage();
    expect(screen.getByText("usb-c")).toBeTruthy();
    expect(screen.getByText("raspberry-pi-5")).toBeTruthy();
    expect(screen.getByText("sbc")).toBeTruthy();
    expect(screen.getByText("connector")).toBeTruthy();
    // dims summary for the pi: pcb 85 x 56 x 1.4 · height_max 18
    expect(screen.getByText(/pcb 85 x 56 x 1\.4/)).toBeTruthy();
    expect(screen.getByText(/height_max 18/)).toBeTruthy();
  });

  it("shows provenance for the learned row plus a source link with the right href", () => {
    renderPage();
    expect(screen.getByText(/learned in cyberdeck, 2026-06-11/)).toBeTruthy();
    const link = screen.getByRole("link", { name: /raspberrypi\.com/ });
    expect(link.getAttribute("href")).toBe("https://raspberrypi.com/pi5");
  });

  it("marks the builtin row as builtin and offers no delete on it", () => {
    renderPage();
    const usbcRow = screen.getByText("usb-c").closest("[role='button']") as HTMLElement;
    expect(within(usbcRow).getByText("builtin")).toBeTruthy();
    expect(within(usbcRow).queryByLabelText(/^Delete /)).toBeNull();
  });

  it("filters the list by search query", async () => {
    renderPage();
    await userEvent.type(screen.getByLabelText("Search references"), "pi");
    expect(screen.getByText("raspberry-pi-5")).toBeTruthy();
    expect(screen.queryByText("usb-c")).toBeNull();
  });

  it("deletes the learned row through its confirm flow", async () => {
    renderPage();
    const piRow = screen.getByText("raspberry-pi-5").closest("[role='button']") as HTMLElement;
    await userEvent.click(within(piRow).getByLabelText("Delete raspberry-pi-5"));
    // Confirm dialog
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /^Delete$/ }));
    expect(remove).toHaveBeenCalledWith("raspberry-pi-5");
  });
});
